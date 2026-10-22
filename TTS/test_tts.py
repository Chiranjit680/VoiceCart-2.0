"""
Tests for the TTS service. Run from the TTS folder:  python test_tts.py

Gnani is replaced by a stand-in, so no key, network or credit is used.
"""
import sys
import time
import traceback

from fastapi.testclient import TestClient

import tts_service
from speech_text import speakable

client = TestClient(tts_service.app)
tests = []


def test(fn):
    tests.append(fn)
    return fn


class patched:
    """Swap a module attribute for the length of a with-block."""

    def __init__(self, name, value):
        self.name, self.value = name, value

    def __enter__(self):
        self.old = getattr(tts_service, self.name)
        setattr(tts_service, self.name, self.value)

    def __exit__(self, *exc):
        setattr(tts_service, self.name, self.old)


@test
def prices_and_units_are_spelled_out():
    assert speakable("Amul Butter 500g is ₹285, with 60 in stock.") == "Amul Butter 500 grams is 285 rupees, with 60 in stock."
    assert speakable("Milk 1L and Rice 5kg") == "Milk 1 litre and Rice 5 kilograms"
    assert speakable("Total ₹1,016.66.") == "Total 1016.66 rupees."
    assert speakable("Save 15% today") == "Save 15 percent today"


@test
def markdown_links_and_emoji_are_dropped():
    assert speakable("**Milk** 🙂 see [the cart](http://x.y/cart) https://foo.bar") == "Milk see the cart"


@test
def nothing_to_say_gives_empty_text():
    assert speakable("🙂🙂") == ""
    assert speakable("   ") == ""


@test
def long_replies_are_cut_at_a_sentence():
    out = speakable("This is a sentence. " * 60)
    assert len(out) <= 600 and out.endswith("sentence."), out[-30:]


@test
def speak_returns_wav_of_the_cleaned_text():
    seen = []
    with patched("synthesize", lambda text: seen.append(text) or b"RIFFdata"):
        response = client.post("/speak", json={"text": "Milk is ₹68."})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFdata"
    assert seen == ["Milk is 68 rupees."], seen


@test
def nothing_speakable_is_204_and_never_calls_gnani():
    def fail(text):
        raise AssertionError("should not be called")
    with patched("synthesize", fail):
        assert client.post("/speak", json={"text": "🙂"}).status_code == 204


@test
def provider_failure_is_502_without_leaking_details():
    def boom(text):
        raise RuntimeError("secret-key-abc rejected")
    with patched("synthesize", boom):
        response = client.post("/speak", json={"text": "hello"})
    assert response.status_code == 502
    assert "secret-key-abc" not in response.text


@test
def slow_provider_is_504():
    with patched("TIMEOUT_SECONDS", 0.05), patched("synthesize", lambda text: time.sleep(0.3) or b"x"):
        assert client.post("/speak", json={"text": "hello"}).status_code == 504


if __name__ == "__main__":
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
