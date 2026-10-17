"""
Tests for the /memories routes. Run from the repo root:  python "Product Service/test_memories_routes.py"

The memory service is replaced by a stand-in, and the login is overridden, so no services or database are used.
"""
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import oauth2  # noqa: E402
from app.config import settings  # noqa: E402
from app.routers import memories  # noqa: E402


def reply(status: int, body=None) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("GET", "http://memory"))


class setup:
    """A tiny app with only the /memories routes, logged in as shopper 5, talking to a recording stand-in service."""

    def __init__(self, answer=None, key="k"):
        self.calls, self.answer, self.key = [], answer or (lambda method, path: reply(200, [])), key

    def __enter__(self):
        self.saved = (settings.memory_service_key, memories.call_memory_service)
        settings.memory_service_key = self.key
        memories.call_memory_service = lambda method, path: (self.calls.append((method, path)), self.answer(method, path))[1]
        app = FastAPI()
        app.include_router(memories.router)
        app.dependency_overrides[oauth2.get_current_user] = lambda: SimpleNamespace(id=5, email="shopper@example.com")
        return TestClient(app), self

    def __exit__(self, *exc):
        settings.memory_service_key, memories.call_memory_service = self.saved


def test_listing_asks_for_the_logged_in_shoppers_memories_only():
    with setup(lambda m, p: reply(200, [{"id": "a", "text": "Is vegetarian."}])) as (client, s):
        response = client.get("/memories")
        assert response.status_code == 200 and response.json() == [{"id": "a", "text": "Is vegetarian."}]
        assert s.calls == [("GET", "/users/5/memories")]


def test_there_is_no_way_to_name_another_shopper():
    with setup() as (client, s):
        client.get("/memories?user_id=9")
        client.delete("/memories/turn-3?user_id=9")
        assert all(path.startswith("/users/5/") for _, path in s.calls), s.calls


def test_forgetting_one_memory():
    with setup(lambda m, p: reply(204)) as (client, s):
        assert client.delete("/memories/turn-3").status_code == 204
        assert s.calls == [("DELETE", "/users/5/memories/turn-3")]
    with setup(lambda m, p: reply(404, {"detail": "No such memory"})) as (client, s):
        assert client.delete("/memories/turn-3").status_code == 404


def test_forgetting_everything():
    with setup(lambda m, p: reply(200, {"deleted": 2})) as (client, s):
        response = client.delete("/memories")
        assert response.status_code == 200 and response.json() == {"deleted": 2}
        assert s.calls == [("DELETE", "/users/5/memories")]


def test_memory_ids_cannot_carry_path_tricks():
    with setup() as (client, s):
        for bad in ("..", "a.b", "a b", "x" * 65):
            assert client.delete(f"/memories/{bad}").status_code in (404, 422), bad
        assert s.calls == []


def test_a_refused_key_is_our_setup_problem_and_looks_like_unavailable_to_the_shopper():
    with setup(lambda m, p: reply(401, {"detail": "Missing or wrong memory service key"})) as (client, s):
        assert client.get("/memories").status_code == 503
        assert client.delete("/memories").status_code == 503


def test_without_a_key_memory_is_reported_as_not_set_up():
    saved = settings.memory_service_key
    settings.memory_service_key = None
    try:
        app = FastAPI()
        app.include_router(memories.router)
        app.dependency_overrides[oauth2.get_current_user] = lambda: SimpleNamespace(id=5)
        response = TestClient(app).get("/memories")
        assert response.status_code == 503 and "not set up" in response.json()["detail"]
    finally:
        settings.memory_service_key = saved


def test_an_unreachable_service_is_a_503_not_a_crash():
    saved = (settings.memory_service_key, settings.memory_service_url)
    settings.memory_service_key, settings.memory_service_url = "k", "http://127.0.0.1:9"  # nothing listens there
    try:
        app = FastAPI()
        app.include_router(memories.router)
        app.dependency_overrides[oauth2.get_current_user] = lambda: SimpleNamespace(id=5)
        assert TestClient(app).get("/memories").status_code == 503
    finally:
        settings.memory_service_key, settings.memory_service_url = saved


def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
