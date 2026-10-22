"""Text-to-speech service: turns an agent reply into a WAV using Gnani's TTS API.

POST /speak {"text": "..."} -> audio/wav. The Gnani key is read from TTS/.env, falling back to STT/.env (the same key).
"""
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from gnani.tts import GnaniTTSClient
from pydantic import BaseModel

from speech_text import speakable

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / "STT" / ".env")  # does not override values already set

log = logging.getLogger("tts")
VOICE = os.environ.get("TTS_VOICE", "Pranav")
MODEL = os.environ.get("TTS_MODEL", "timbre-v2.5")
LANGUAGE = os.environ.get("TTS_LANGUAGE", "en-IN")  # timbre-v2.5 only
SPEED = float(os.environ["TTS_SPEED"]) if os.environ.get("TTS_SPEED") else None  # only used by timbre-v2.5
TIMEOUT_SECONDS = float(os.environ.get("TTS_TIMEOUT", "20"))

app = FastAPI(title="VoiceCart TTS")
_client: GnaniTTSClient | None = None


def get_client() -> GnaniTTSClient:
    global _client
    if _client is None:
        key = os.environ.get("GNANI_API_KEY")
        if not key:
            raise RuntimeError("GNANI_API_KEY is not set")
        _client = GnaniTTSClient(api_key=key)
    return _client


class SpeakRequest(BaseModel):
    text: str


def synthesize(text: str) -> bytes:
    options = {"model": MODEL}
    if MODEL == "timbre-v2.5":
        options.update(language=LANGUAGE, speed=SPEED)
    return get_client().synthesize(text, VOICE, **options)


@app.get("/health")
def health():
    return {"status": "ok", "voice": VOICE, "model": MODEL, "key_set": bool(os.environ.get("GNANI_API_KEY"))}


@app.post("/speak")
async def speak(body: SpeakRequest):
    text = speakable(body.text)
    if not text:
        return Response(status_code=204)  # nothing worth saying aloud
    try:
        audio = await asyncio.wait_for(asyncio.to_thread(synthesize, text), TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(504, "The speech service took too long")
    except Exception as exc:
        log.warning("synthesis failed: %s", type(exc).__name__)  # never log the request, which carries the key
        raise HTTPException(502, "The speech service could not make audio")
    return Response(content=audio, media_type="audio/wav")
