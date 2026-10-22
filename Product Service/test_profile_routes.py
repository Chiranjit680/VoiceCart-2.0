"""
Tests for the /profile routes. Run from the repo root:  python "Product Service/test_profile_routes.py"

The database is replaced by a tiny in-memory stand-in and the login is overridden, so nothing external is used.
"""
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database, models, oauth2  # noqa: E402
from app.routers import profile  # noqa: E402


class FakeDb:
    def __init__(self):
        self.rows = {}

    def get(self, model, key):
        return self.rows.get(key)

    def add(self, row):
        self.rows[row.user_id] = row

    def commit(self):
        pass

    def refresh(self, row):
        pass


def client_for(user_id, db):
    app = FastAPI()
    app.include_router(profile.router)
    app.dependency_overrides[oauth2.get_current_user] = lambda: SimpleNamespace(id=user_id)
    app.dependency_overrides[database.get_db] = lambda: db
    return TestClient(app)


def test_a_new_shopper_gets_an_empty_profile_not_a_404():
    response = client_for(5, FakeDb()).get("/profile")
    assert response.status_code == 200
    assert response.json() == {"age": None, "preferences": [], "medical_conditions": []}


def test_saving_then_reading_back():
    db = FakeDb()
    client = client_for(5, db)
    body = {"age": 34, "preferences": ["vegetarian", "Amul only"], "medical_conditions": ["diabetes"]}
    saved = client.put("/profile", json=body)
    assert saved.status_code == 200 and saved.json() == body
    assert client.get("/profile").json() == body
    assert list(db.rows) == [5]


def test_saving_again_replaces_everything_and_can_clear_fields():
    db = FakeDb()
    client = client_for(5, db)
    client.put("/profile", json={"age": 34, "preferences": ["vegan"], "medical_conditions": ["asthma"]})
    cleared = client.put("/profile", json={"age": None, "preferences": [], "medical_conditions": []})
    assert cleared.json() == {"age": None, "preferences": [], "medical_conditions": []}
    assert len(db.rows) == 1


def test_each_shopper_only_sees_their_own_row():
    db = FakeDb()
    client_for(5, db).put("/profile", json={"age": 40, "preferences": ["keto"], "medical_conditions": []})
    other = client_for(6, db).get("/profile")
    assert other.json() == {"age": None, "preferences": [], "medical_conditions": []}
    client_for(6, db).put("/profile", json={"age": 22, "preferences": [], "medical_conditions": []})
    assert db.rows[5].age == 40 and db.rows[6].age == 22


def test_there_is_no_way_to_name_another_shopper():
    db = FakeDb()
    client_for(5, db).put("/profile?user_id=9", json={"user_id": 9, "age": 40, "preferences": [], "medical_conditions": []})
    assert list(db.rows) == [5]


def test_entries_are_trimmed_deduplicated_and_blanks_dropped():
    response = client_for(5, FakeDb()).put("/profile", json={
        "age": 30, "preferences": ["  vegan ", "Vegan", "", "   ", "low  salt"], "medical_conditions": [],
    })
    assert response.json()["preferences"] == ["vegan", "low salt"]


def test_bad_values_are_rejected():
    client = client_for(5, FakeDb())
    assert client.put("/profile", json={"age": -1}).status_code == 422
    assert client.put("/profile", json={"age": 121}).status_code == 422
    assert client.put("/profile", json={"preferences": ["x" * 81]}).status_code == 422
    assert client.put("/profile", json={"medical_conditions": [f"c{i}" for i in range(31)]}).status_code == 422
    assert client.put("/profile", json={"age": "abc"}).status_code == 422


def test_the_table_is_created_with_the_model():
    table = models.UserProfile.__table__
    assert table.name == "user_profiles"
    assert {c.name for c in table.columns} == {"user_id", "age", "preferences", "medical_conditions", "updated_at"}
    assert table.c.user_id.primary_key
    assert next(iter(table.c.user_id.foreign_keys)).ondelete == "CASCADE"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
