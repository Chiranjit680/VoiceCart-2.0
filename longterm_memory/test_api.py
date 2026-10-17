"""
Tests for the memory service's HTTP API. Run from the repo root:  python -m longterm_memory.test_api

They use a stand-in collection that records each call, so they need neither Chroma nor a database.
"""
import sys
import traceback

from fastapi.testclient import TestClient

from . import api
from .test_user_memory import RecordingCollection, meta

KEY = "test-key"
HEADERS = {"X-Memory-Key": KEY}


def client(collection=None, key=KEY) -> TestClient:
    collection = collection if collection is not None else RecordingCollection()
    return TestClient(api.create_app(key=key, get_collection=lambda: collection, run_poller=False))


def where_filters(collection) -> list:
    return [kwargs["where"] for name, kwargs in collection.calls if "where" in kwargs]


def test_every_route_needs_the_key():
    collection = RecordingCollection()
    c = client(collection)
    requests = [
        ("POST", "/users/3/search", {"json": {"query": "milk"}}),
        ("GET", "/users/3/memories", {}),
        ("DELETE", "/users/3/memories/m1", {}),
        ("DELETE", "/users/3/memories", {}),
    ]
    for method, path, extra in requests:
        assert c.request(method, path, **extra).status_code == 401, f"{method} {path} without a key"
        assert c.request(method, path, headers={"X-Memory-Key": "wrong"}, **extra).status_code == 401, f"{method} {path} with a wrong key"
        assert c.request(method, path, headers={"X-Memory-Key": ""}, **extra).status_code == 401
    assert collection.calls == []  # a refused request never reached the memories


def test_health_needs_no_key_and_reveals_nothing_about_shoppers():
    response = client().get("/health")
    assert response.status_code == 200
    assert set(response.json()) == {"ok", "poller_running"}


def test_the_service_will_not_start_without_a_key(monkeypatch=None):
    original = api.service_key
    api.service_key = lambda: None
    try:
        api.create_app(key=None, run_poller=False, get_collection=lambda: None)
    except RuntimeError as error:
        assert "MEMORY_SERVICE_KEY" in str(error)
    else:
        raise AssertionError("started without a key")
    finally:
        api.service_key = original


def test_search_is_scoped_to_the_shopper_in_the_path():
    collection = RecordingCollection(ids=["u3:m1"], documents=["Is vegetarian."], metadatas=[meta(3)], distances=[0.2])
    response = client(collection).post("/users/3/search", json={"query": "dinner", "k": 4}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == [{"id": "m1", "text": "Is vegetarian.", "kind": "dietary", "created_at": 100.0, "distance": 0.2}]
    assert where_filters(collection) == [{"user_id": "3"}]


def test_a_memory_that_is_not_the_shoppers_is_never_returned():
    collection = RecordingCollection(ids=["u9:x"], documents=["Someone else's."], metadatas=[meta(9)])
    response = client(collection).post("/users/3/search", json={"query": "anything"}, headers=HEADERS)
    assert response.status_code == 200 and response.json() == []


def test_bad_user_ids_and_bodies_are_rejected_before_any_memory_is_touched():
    collection = RecordingCollection()
    c = client(collection)
    for user in ("0", "-1", "abc", "1.5"):
        assert c.post(f"/users/{user}/search", json={"query": "x"}, headers=HEADERS).status_code == 422, user
        assert c.get(f"/users/{user}/memories", headers=HEADERS).status_code == 422, user
    for body in ({"query": ""}, {"query": "x", "k": 0}, {"query": "x", "k": 11}, {}, {"query": "x" * 1001}):
        assert c.post("/users/3/search", json=body, headers=HEADERS).status_code == 422, body
    assert collection.calls == []


def test_listing_is_scoped_and_paged():
    ids = [f"u3:m{n}" for n in range(3)]
    collection = RecordingCollection(ids=ids, documents=["a", "b", "c"], metadatas=[meta(3, ) for _ in ids])
    response = client(collection).get("/users/3/memories?limit=2&offset=1", headers=HEADERS)
    assert response.status_code == 200 and len(response.json()) == 2
    assert where_filters(collection) == [{"user_id": "3"}]
    assert client(collection).get("/users/3/memories?limit=0", headers=HEADERS).status_code == 422


def test_deleting_a_memory_that_is_not_theirs_is_a_404():
    collection = RecordingCollection(ids=[])
    response = client(collection).delete("/users/3/memories/someone-elses", headers=HEADERS)
    assert response.status_code == 404
    assert [name for name, _ in collection.calls] == ["get"]  # nothing was deleted


def test_deleting_their_own_memory_works():
    collection = RecordingCollection(ids=["u3:m1"], documents=["x"], metadatas=[meta(3)])
    response = client(collection).delete("/users/3/memories/m1", headers=HEADERS)
    assert response.status_code == 204
    deletes = [kw for name, kw in collection.calls if name == "delete"]
    assert deletes == [{"ids": ["u3:m1"], "where": {"user_id": "3"}}]


def test_memory_ids_cannot_carry_path_tricks():
    collection = RecordingCollection()
    c = client(collection)
    for bad in ("..", "a.b", "a b", "x" * 65, "a%00b"):
        assert c.delete(f"/users/3/memories/{bad}", headers=HEADERS).status_code in (404, 422), bad
    assert collection.calls == []


def test_forget_everything_reports_how_many_and_stays_scoped():
    collection = RecordingCollection(ids=["u3:a", "u3:b"], documents=["x", "y"], metadatas=[meta(3), meta(3)])
    response = client(collection).delete("/users/3/memories", headers=HEADERS)
    assert response.status_code == 200 and response.json() == {"deleted": 2}
    deletes = [kw for name, kw in collection.calls if name == "delete"]
    assert deletes == [{"ids": ["u3:a", "u3:b"], "where": {"user_id": "3"}}]


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
