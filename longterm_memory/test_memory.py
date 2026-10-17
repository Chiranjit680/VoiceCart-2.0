"""
Tests for the memory service. Run from the repo root:  python -m longterm_memory.test_memory   (or pytest)

They use a throwaway Postgres schema that copies chat_sessions/chat_turns, so real rows are never read or
changed, and a fake judge and store, so neither the model nor Chroma is needed.
"""
import contextlib
import sys
import traceback
import uuid
from pathlib import Path

import psycopg

from .memory import MemoryService, SchemaError, database_url
from .models import Turn, Verdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Product Service"))
from app.migrations import STATEMENTS  # noqa: E402  (the real migration, so the test checks what the app runs)


class FakeJudge:
    def __init__(self, decide=None):
        self.decide = decide or (lambda turn, context: Verdict(False))
        self.calls = []  # (turn, context)

    def judge(self, turn, context):
        self.calls.append((turn, list(context)))
        return self.decide(turn, context)


class FakeStore:
    def __init__(self):
        self.added = []

    def add(self, **kwargs):
        self.added.append(kwargs)


@contextlib.contextmanager
def scratch(with_flag_columns: bool = True):
    """A schema holding empty copies of the chat tables; yields (connect_factory, admin_connection)."""
    url = database_url()
    name = f"memtest_{uuid.uuid4().hex[:8]}"
    admin = psycopg.connect(url, autocommit=True)
    admin.execute(f"CREATE SCHEMA {name}")
    try:
        admin.execute(f"CREATE TABLE {name}.chat_sessions (LIKE public.chat_sessions INCLUDING ALL)")
        admin.execute(f"CREATE TABLE {name}.chat_turns (LIKE public.chat_turns INCLUDING ALL)")
        if not with_flag_columns:
            admin.execute(f"ALTER TABLE {name}.chat_turns DROP COLUMN checked, DROP COLUMN longterm")
        admin.execute(f"SET search_path = {name}")  # the admin connection sees the scratch tables too
        yield (lambda: psycopg.connect(url, autocommit=True, options=f"-c search_path={name}")), admin
    finally:
        admin.execute("SET search_path = public")
        admin.execute(f"DROP SCHEMA {name} CASCADE")
        admin.close()


def add_session(admin, session_id: str, user_id: int):
    admin.execute("INSERT INTO chat_sessions (id, user_id, turn_count) VALUES (%s, %s, 0)", (session_id, user_id))


def add_turn(admin, turn_id: int, session_id: str, seq: int, role: str, content: str, checked: bool = False):
    admin.execute(
        "INSERT INTO chat_turns (id, session_id, seq, role, content, checked) VALUES (%s, %s, %s, %s, %s, %s)",
        (turn_id, session_id, seq, role, content, checked),
    )


def flags(admin):
    return {row[0]: (row[1], row[2]) for row in admin.execute("SELECT id, checked, longterm FROM chat_turns ORDER BY id")}


def service(connect, judge, store, **kwargs):
    return MemoryService(connect, judge, store, **kwargs)


# --- tests ---

def test_saves_what_the_judge_picks_and_flags_every_turn():
    with scratch() as (connect, admin):
        add_session(admin, "s1", user_id=7)
        add_turn(admin, 1, "s1", 1, "user", "I'm vegetarian")
        add_turn(admin, 2, "s1", 2, "assistant", "Noted! Anything else?")
        add_turn(admin, 3, "s1", 3, "user", "add two of those to my cart")
        judge = FakeJudge(lambda t, c: Verdict(True, "Is vegetarian.", "dietary") if "vegetarian" in t.content else Verdict(False))
        store = FakeStore()

        result = service(connect, judge, store).process_batch()

        assert (result.checked, result.remembered, result.failed) == (3, 1, 0)
        assert flags(admin) == {1: (True, True), 2: (True, False), 3: (True, False)}
        assert store.added == [{"memory_id": "turn-1", "user_id": 7, "text": "Is vegetarian.", "kind": "dietary",
                                "source": {"session_id": "s1", "turn_id": 1}}]


def test_assistant_replies_are_never_sent_to_the_judge():
    with scratch() as (connect, admin):
        add_session(admin, "s1", 1)
        add_turn(admin, 1, "s1", 1, "assistant", "I live in Guwahati, says the assistant")
        judge = FakeJudge(lambda t, c: Verdict(True, "x"))
        service(connect, judge, FakeStore()).process_batch()
        assert judge.calls == []
        assert flags(admin) == {1: (True, False)}


def test_the_judge_sees_the_earlier_turns_of_the_same_session_oldest_first():
    with scratch() as (connect, admin):
        add_session(admin, "a", 1)
        add_session(admin, "b", 2)
        for seq in range(1, 6):
            add_turn(admin, seq, "a", seq, "assistant" if seq % 2 == 0 else "user", f"a{seq}", checked=seq != 5)
        add_turn(admin, 10, "b", 1, "user", "other session", checked=True)
        judge = FakeJudge()
        service(connect, judge, FakeStore(), context_turns=3).process_batch()
        (turn, context), = judge.calls
        assert turn.content == "a5"
        assert [t.content for t in context] == ["a2", "a3", "a4"]  # the 3 turns before it, oldest first, same session only


def test_a_judge_failure_leaves_the_turn_unchecked_and_the_rest_are_processed():
    with scratch() as (connect, admin):
        add_session(admin, "s", 1)
        add_turn(admin, 1, "s", 1, "user", "boom")
        add_turn(admin, 2, "s", 2, "user", "fine")

        def decide(turn, context):
            if turn.content == "boom":
                raise RuntimeError("model unreachable")
            return Verdict(False)

        result = service(connect, FakeJudge(decide), FakeStore()).process_batch()
        assert (result.checked, result.failed) == (1, 1)
        assert flags(admin) == {1: (False, False), 2: (True, False)}

        again = service(connect, FakeJudge(), FakeStore()).process_batch()  # the model is back
        assert again.checked == 1
        assert flags(admin)[1] == (True, False)


def test_a_store_failure_also_leaves_the_turn_unchecked():
    with scratch() as (connect, admin):
        add_session(admin, "s", 1)
        add_turn(admin, 1, "s", 1, "user", "I'm allergic to peanuts")

        class BrokenStore:
            def add(self, **_):
                raise OSError("disk full")

        result = service(connect, FakeJudge(lambda t, c: Verdict(True, "Allergic to peanuts.")), BrokenStore()).process_batch()
        assert result.failed == 1
        assert flags(admin) == {1: (False, False)}  # not flagged, so it is retried instead of silently lost


def test_a_dry_run_changes_nothing():
    with scratch() as (connect, admin):
        add_session(admin, "s", 1)
        add_turn(admin, 1, "s", 1, "user", "I only buy Amul")
        store = FakeStore()
        result = service(connect, FakeJudge(lambda t, c: Verdict(True, "Only buys Amul.")), store).process_batch(dry_run=True)
        assert (result.checked, result.remembered) == (1, 1)  # what it would do
        assert store.added == []
        assert flags(admin) == {1: (False, False)}


def test_checked_turns_are_not_looked_at_again():
    with scratch() as (connect, admin):
        add_session(admin, "s", 1)
        add_turn(admin, 1, "s", 1, "user", "hello")
        judge = FakeJudge()
        svc = service(connect, judge, FakeStore())
        assert svc.process_batch().checked == 1
        assert svc.process_batch().checked == 0
        assert len(judge.calls) == 1


def test_remember_with_no_text_is_not_saved():
    with scratch() as (connect, admin):
        add_session(admin, "s", 1)
        add_turn(admin, 1, "s", 1, "user", "something")
        store = FakeStore()
        service(connect, FakeJudge(lambda t, c: Verdict(True, "   ")), store).process_batch()
        assert store.added == []
        assert flags(admin) == {1: (True, False)}


def test_batches_are_taken_in_order_and_limited():
    with scratch() as (connect, admin):
        add_session(admin, "s", 1)
        for i in range(1, 6):
            add_turn(admin, i, "s", i, "user", f"m{i}")
        svc = service(connect, FakeJudge(), FakeStore(), batch_size=2)
        assert svc.process_batch().checked == 2
        assert [i for i, (checked, _) in flags(admin).items() if checked] == [1, 2]
        assert svc.process_batch().checked == 2
        assert svc.process_batch().checked == 1
        assert svc.process_batch().checked == 0


def test_a_turn_whose_session_is_gone_is_simply_not_seen():
    # chat_turns.session_id has a foreign key with ON DELETE CASCADE in the real tables, so this cannot happen
    # there; this test only pins that the join does not break the batch if such a row ever appears.
    with scratch() as (connect, admin):
        add_session(admin, "s", 1)
        add_turn(admin, 1, "s", 1, "user", "hi")
        add_turn(admin, 2, "ghost", 1, "user", "orphan")
        assert service(connect, FakeJudge(), FakeStore()).process_batch().checked == 1


def test_ensure_schema_explains_a_missing_migration():
    with scratch(with_flag_columns=False) as (connect, admin):
        try:
            service(connect, FakeJudge(), FakeStore()).ensure_schema()
        except SchemaError as error:
            assert "Product Service" in str(error)
        else:
            raise AssertionError("expected SchemaError")
    with scratch() as (connect, admin):
        service(connect, FakeJudge(), FakeStore()).ensure_schema()  # present: no error


def test_the_migration_adds_the_columns_to_an_existing_table_and_can_be_repeated():
    with scratch(with_flag_columns=False) as (connect, admin):
        add_session(admin, "s", 1)
        admin.execute("INSERT INTO chat_turns (id, session_id, seq, role, content) VALUES (1, 's', 1, 'user', 'old row')")
        for _ in range(2):  # the second run must change nothing and not fail
            for statement in STATEMENTS:
                admin.execute(statement)
        assert flags(admin) == {1: (False, False)}  # existing rows start unchecked, not long-term
        index = admin.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_chat_turns_unchecked' AND schemaname = current_schema()").fetchone()
        assert index and "WHERE (checked = false)" in index[0]


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
    raise SystemExit(main())
