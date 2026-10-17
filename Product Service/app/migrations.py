"""
Schema changes that `create_all` cannot make: it only creates tables that are missing and never alters
existing ones. Every statement is safe to run again, and the app applies them all at startup.
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

STATEMENTS = [
    # chat_turns.checked / chat_turns.longterm, used by the long-term memory service (see longterm_memory/).
    # Adding a column with a constant default is instant in Postgres 11+, even on a big table.
    "ALTER TABLE chat_turns ADD COLUMN IF NOT EXISTS checked boolean NOT NULL DEFAULT false",
    "ALTER TABLE chat_turns ADD COLUMN IF NOT EXISTS longterm boolean NOT NULL DEFAULT false",
    "CREATE INDEX IF NOT EXISTS ix_chat_turns_unchecked ON chat_turns (id) WHERE checked = false",
]


def apply_migrations(engine: Engine) -> None:
    with engine.begin() as connection:  # one transaction: all of it or none of it
        for statement in STATEMENTS:
            connection.execute(text(statement))
