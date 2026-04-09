import pytest
import sqlite3


def test_database_creates_all_tables(db):
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t[0] for t in tables]

    assert "users" in table_names
    assert "channels" in table_names
    assert "messages" in table_names
    assert "reactions" in table_names
    assert "huddles" in table_names
    assert "files" in table_names
    assert "pins" in table_names
    assert "mentions" in table_names
    assert "sync_state" in table_names
    assert "weekly_stats" in table_names
    assert "monthly_stats" in table_names
    assert "ai_insights" in table_names


def test_database_creates_fts_table(db):
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'"
    ).fetchall()
    assert len(tables) == 1


def test_database_creates_indexes(db):
    indexes = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    ).fetchall()
    index_names = [i[0] for i in indexes]

    assert "idx_messages_channel_created" in index_names
    assert "idx_messages_user_channel" in index_names
    assert "idx_messages_thread" in index_names
    assert "idx_reactions_message" in index_names
    assert "idx_reactions_user" in index_names


def test_insert_and_read_user(db):
    db.execute(
        "INSERT INTO users (slack_id, name, display_name, real_name) VALUES (?, ?, ?, ?)",
        ("U12345", "jdoe", "John", "John Doe"),
    )
    db.commit()

    row = db.execute("SELECT * FROM users WHERE slack_id = ?", ("U12345",)).fetchone()
    assert row is not None
    assert row["slack_id"] == "U12345"
    assert row["name"] == "jdoe"


def test_insert_message_unique_constraint(db):
    db.execute(
        "INSERT INTO channels (slack_id, name, type) VALUES (?, ?, ?)",
        ("C1", "general", "channel"),
    )
    db.execute(
        "INSERT INTO users (slack_id, name) VALUES (?, ?)",
        ("U1", "alice"),
    )
    db.commit()

    db.execute(
        "INSERT INTO messages (channel_id, user_id, slack_ts, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (1, 1, "1700000000.000001", "hello", 1700000000.0),
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO messages (channel_id, user_id, slack_ts, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (1, 1, "1700000000.000001", "duplicate", 1700000000.0),
        )


def test_schema_version(db):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    assert version == 1


def test_upsert_user(db):
    db.upsert_user(slack_id="U1", name="alice", display_name="Alice", real_name="Alice Smith")
    db.upsert_user(slack_id="U1", name="alice", display_name="Alice Updated", real_name="Alice Smith")

    rows = db.execute("SELECT * FROM users WHERE slack_id = ?", ("U1",)).fetchall()
    assert len(rows) == 1
    assert rows[0]["display_name"] == "Alice Updated"


def test_upsert_channel(db):
    db.upsert_channel(slack_id="C1", name="general", type="channel")
    db.upsert_channel(slack_id="C1", name="general-renamed", type="channel")

    rows = db.execute("SELECT * FROM channels WHERE slack_id = ?", ("C1",)).fetchall()
    assert len(rows) == 1
    assert rows[0]["name"] == "general-renamed"


def test_upsert_message(db):
    db.upsert_channel(slack_id="C1", name="general", type="channel")
    ch_id = db.execute("SELECT id FROM channels WHERE slack_id = ?", ("C1",)).fetchone()["id"]
    db.upsert_user(slack_id="U1", name="alice")
    u_id = db.execute("SELECT id FROM users WHERE slack_id = ?", ("U1",)).fetchone()["id"]

    db.upsert_message(
        channel_id=ch_id, user_id=u_id, slack_ts="1700000000.000001",
        text="hello", created_at=1700000000.0,
    )
    db.upsert_message(
        channel_id=ch_id, user_id=u_id, slack_ts="1700000000.000001",
        text="hello edited", created_at=1700000000.0,
    )

    rows = db.execute("SELECT * FROM messages WHERE slack_ts = ?", ("1700000000.000001",)).fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "hello edited"
