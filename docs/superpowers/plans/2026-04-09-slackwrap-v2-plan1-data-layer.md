# SlackWrap v2 — Plan 1: Data Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the JSON cache with a normalized SQLite database, build a robust sync engine that fetches Slack data once and supports incremental delta syncs, and store all data locally at `~/.slackwrap/data.db`.

**Architecture:** SQLite database with normalized tables (users, channels, messages, reactions, huddles, files, pins, mentions), FTS5 for text search, sync state tracking per channel. The sync engine handles initial full sync and incremental delta sync in phases. All existing Slack API interactions are preserved and new endpoints are added.

**Tech Stack:** Python 3.10+, sqlite3 (stdlib), requests, python-dotenv

**Spec:** `docs/superpowers/specs/2026-04-09-slackwrap-v2-design.md`

---

## File Structure

```
src/
  slackwrap/
    __init__.py
    db.py                  # Database connection, schema creation, migrations
    models.py              # Dataclasses for all domain objects
    slack_client.py        # Slack API client (refactored from existing)
    sync.py                # Sync engine — orchestrates fetch + store
    config.py              # App config, paths (~/.slackwrap/)
tests/
  __init__.py
  test_db.py
  test_models.py
  test_slack_client.py
  test_sync.py
  test_config.py
  conftest.py             # Shared fixtures (in-memory DB, mock client)
```

**Note:** We are moving from `src/` flat layout to `src/slackwrap/` package. The old files (`src/main.py`, `src/cache.py`, etc.) remain untouched in this plan — they will be replaced in later plans. This plan builds the new foundation alongside the old code.

---

### Task 1: Project Setup — Config and Paths

**Files:**
- Create: `src/slackwrap/__init__.py`
- Create: `src/slackwrap/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create package init**

```python
# src/slackwrap/__init__.py
```

Empty file. Establishes the `slackwrap` package under `src/`.

- [ ] **Step 2: Write failing test for config**

```python
# tests/test_config.py
import os
import tempfile
from pathlib import Path


def test_default_data_dir_is_home_slackwrap():
    from slackwrap.config import SlackWrapConfig

    config = SlackWrapConfig()
    expected = Path.home() / ".slackwrap"
    assert config.data_dir == expected


def test_custom_data_dir():
    from slackwrap.config import SlackWrapConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        config = SlackWrapConfig(data_dir=Path(tmpdir))
        assert config.data_dir == Path(tmpdir)


def test_db_path():
    from slackwrap.config import SlackWrapConfig

    config = SlackWrapConfig()
    assert config.db_path == Path.home() / ".slackwrap" / "data.db"


def test_ensure_dirs_creates_data_dir():
    from slackwrap.config import SlackWrapConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "slackwrap_test"
        config = SlackWrapConfig(data_dir=data_dir)
        config.ensure_dirs()
        assert data_dir.exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/maverick/code/projects/open-source/SlackWrap && python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackwrap'`

- [ ] **Step 4: Update pyproject.toml for new package layout**

Modify: `pyproject.toml` — change the package source so both `src` (legacy) and `src/slackwrap` (new) are discoverable.

```toml
[project]
name = "slackwrap"
version = "2.0.0"
description = "Your Slack year in review — huddle and message analytics"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
dependencies = [
    "requests>=2.31.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[project.scripts]
slackwrap = "slackwrap.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 5: Implement config**

```python
# src/slackwrap/config.py
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SlackWrapConfig:
    data_dir: Path = field(default_factory=lambda: Path.home() / ".slackwrap")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "data.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/slackwrap/__init__.py src/slackwrap/config.py tests/test_config.py pyproject.toml
git commit -m "feat(v2): add SlackWrapConfig with data dir and db path"
```

---

### Task 2: Domain Models

**Files:**
- Create: `src/slackwrap/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for models**

```python
# tests/test_models.py
from datetime import datetime, timezone


def test_user_creation():
    from slackwrap.models import User

    user = User(
        id=1,
        slack_id="U12345",
        name="jdoe",
        display_name="John",
        real_name="John Doe",
    )
    assert user.slack_id == "U12345"
    assert user.is_bot is False
    assert user.timezone is None


def test_channel_creation():
    from slackwrap.models import Channel

    ch = Channel(id=1, slack_id="C12345", name="general", type="channel")
    assert ch.type == "channel"
    assert ch.is_archived is False


def test_message_is_thread_reply():
    from slackwrap.models import Message

    parent = Message(
        id=1, channel_id=1, user_id=1, slack_ts="1700000000.000001",
        text="hello", created_at=1700000000.0,
        thread_ts="1700000000.000001",
    )
    assert parent.is_thread_reply is False

    reply = Message(
        id=2, channel_id=1, user_id=1, slack_ts="1700000001.000001",
        text="world", created_at=1700000001.0,
        thread_ts="1700000000.000001",
    )
    assert reply.is_thread_reply is True


def test_huddle_duration():
    from slackwrap.models import Huddle

    huddle = Huddle(
        id=1, channel_id=1, created_by_user_id=1,
        started_at=1700000000.0, ended_at=1700003600.0,
        participant_ids=[1, 2],
    )
    assert huddle.duration_seconds == 3600


def test_reaction_creation():
    from slackwrap.models import Reaction

    r = Reaction(id=1, message_id=1, user_id=1, emoji_name="thumbsup")
    assert r.emoji_name == "thumbsup"


def test_file_creation():
    from slackwrap.models import File

    f = File(
        id=1, channel_id=1, user_id=1, slack_file_id="F12345",
        name="report.pdf", filetype="pdf", size_bytes=1024, created_at=1700000000.0,
    )
    assert f.filetype == "pdf"
    assert f.size_bytes == 1024


def test_pin_creation():
    from slackwrap.models import Pin

    p = Pin(id=1, channel_id=1, user_id=1, message_ts="1700000000.000001", pinned_at=1700000100.0)
    assert p.message_ts == "1700000000.000001"


def test_sync_state_creation():
    from slackwrap.models import SyncState

    s = SyncState(channel_id=1, last_synced_ts="1700000000.000001", last_synced_at=1700000100.0)
    assert s.status == "pending"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement models**

```python
# src/slackwrap/models.py
from dataclasses import dataclass, field


@dataclass
class User:
    id: int
    slack_id: str
    name: str | None = None
    display_name: str | None = None
    real_name: str | None = None
    is_bot: bool = False
    timezone: str | None = None
    tz_offset: int | None = None
    title: str | None = None
    start_date: str | None = None
    status_text: str | None = None
    status_emoji: str | None = None
    locale: str | None = None
    avatar_url: str | None = None
    synced_at: float | None = None


@dataclass
class Channel:
    id: int
    slack_id: str
    name: str | None = None
    type: str = "channel"  # 'dm', 'channel', 'group', 'mpim'
    created_at: float | None = None
    topic: str | None = None
    purpose: str | None = None
    num_members: int | None = None
    is_archived: bool = False
    synced_at: float | None = None


@dataclass
class Message:
    id: int
    channel_id: int
    user_id: int | None
    slack_ts: str
    text: str | None = None
    created_at: float = 0.0
    subtype: str | None = None
    thread_ts: str | None = None
    reply_count: int = 0
    files_count: int = 0

    @property
    def is_thread_reply(self) -> bool:
        return self.thread_ts is not None and self.thread_ts != self.slack_ts


@dataclass
class Reaction:
    id: int
    message_id: int
    user_id: int
    emoji_name: str


@dataclass
class Huddle:
    id: int
    channel_id: int
    created_by_user_id: int | None
    started_at: float
    ended_at: float
    participant_ids: list[int] = field(default_factory=list)

    @property
    def duration_seconds(self) -> int:
        return int(self.ended_at - self.started_at)


@dataclass
class File:
    id: int
    channel_id: int | None
    user_id: int | None
    slack_file_id: str
    name: str | None = None
    filetype: str | None = None
    size_bytes: int | None = None
    created_at: float | None = None


@dataclass
class Pin:
    id: int
    channel_id: int
    user_id: int | None
    message_ts: str | None = None
    pinned_at: float | None = None


@dataclass
class Mention:
    id: int
    channel_id: int | None
    from_user_id: int | None
    mentioned_user_id: int | None
    message_ts: str | None = None
    context_text: str | None = None


@dataclass
class SyncState:
    channel_id: int
    last_synced_ts: str | None = None
    last_synced_at: float | None = None
    status: str = "pending"  # 'pending', 'syncing', 'complete', 'error'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/models.py tests/test_models.py
git commit -m "feat(v2): add domain models — User, Channel, Message, Huddle, Reaction, File, Pin, SyncState"
```

---

### Task 3: Database Schema and Connection

**Files:**
- Create: `src/slackwrap/db.py`
- Create: `tests/test_db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create shared test fixtures**

```python
# tests/conftest.py
import pytest
from slackwrap.db import Database


@pytest.fixture
def db():
    """In-memory database for testing."""
    database = Database(":memory:")
    database.initialize()
    yield database
    database.close()
```

- [ ] **Step 2: Write failing tests for schema creation**

```python
# tests/test_db.py

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
    import sqlite3

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


import pytest
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — `ImportError: cannot import name 'Database' from 'slackwrap.db'`

- [ ] **Step 4: Implement Database class with schema**

```python
# src/slackwrap/db.py
import sqlite3
import time

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slack_id TEXT UNIQUE NOT NULL,
    name TEXT,
    display_name TEXT,
    real_name TEXT,
    is_bot INTEGER DEFAULT 0,
    timezone TEXT,
    tz_offset INTEGER,
    title TEXT,
    start_date TEXT,
    status_text TEXT,
    status_emoji TEXT,
    locale TEXT,
    avatar_url TEXT,
    synced_at REAL
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slack_id TEXT UNIQUE NOT NULL,
    name TEXT,
    type TEXT NOT NULL DEFAULT 'channel',
    created_at REAL,
    topic TEXT,
    purpose TEXT,
    num_members INTEGER,
    is_archived INTEGER DEFAULT 0,
    synced_at REAL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    user_id INTEGER REFERENCES users(id),
    slack_ts TEXT NOT NULL,
    text TEXT,
    subtype TEXT,
    thread_ts TEXT,
    reply_count INTEGER DEFAULT 0,
    files_count INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    UNIQUE(channel_id, slack_ts)
);

CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    emoji_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS huddles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    created_by_user_id INTEGER REFERENCES users(id),
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL,
    duration_seconds INTEGER,
    participant_ids TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER REFERENCES channels(id),
    user_id INTEGER REFERENCES users(id),
    slack_file_id TEXT UNIQUE NOT NULL,
    name TEXT,
    filetype TEXT,
    size_bytes INTEGER,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    user_id INTEGER REFERENCES users(id),
    message_ts TEXT,
    pinned_at REAL
);

CREATE TABLE IF NOT EXISTS mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER REFERENCES channels(id),
    from_user_id INTEGER REFERENCES users(id),
    mentioned_user_id INTEGER REFERENCES users(id),
    message_ts TEXT,
    context_text TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    channel_id INTEGER PRIMARY KEY REFERENCES channels(id),
    last_synced_ts TEXT,
    last_synced_at REAL,
    status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS weekly_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_key TEXT NOT NULL,
    week_start TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    your_count INTEGER DEFAULT 0,
    their_count INTEGER DEFAULT 0,
    avg_response_seconds REAL,
    huddle_count INTEGER DEFAULT 0,
    huddle_seconds INTEGER DEFAULT 0,
    avg_word_count_you REAL,
    avg_word_count_them REAL,
    emoji_count INTEGER DEFAULT 0,
    reaction_count INTEGER DEFAULT 0,
    UNIQUE(relationship_key, week_start)
);

CREATE TABLE IF NOT EXISTS monthly_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_key TEXT NOT NULL,
    month TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    your_count INTEGER DEFAULT 0,
    their_count INTEGER DEFAULT 0,
    avg_response_seconds REAL,
    huddle_count INTEGER DEFAULT 0,
    huddle_seconds INTEGER DEFAULT 0,
    avg_word_count_you REAL,
    avg_word_count_them REAL,
    emoji_count INTEGER DEFAULT 0,
    reaction_count INTEGER DEFAULT 0,
    tone_label TEXT,
    UNIQUE(relationship_key, month)
);

CREATE TABLE IF NOT EXISTS ai_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_key TEXT NOT NULL,
    insight_type TEXT NOT NULL,
    model_name TEXT,
    input_hash TEXT,
    result_json TEXT NOT NULL,
    generated_at REAL
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text, content=messages, content_rowid=id
);

CREATE INDEX IF NOT EXISTS idx_messages_channel_created ON messages(channel_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_user_channel ON messages(user_id, channel_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(channel_id, thread_ts);
CREATE INDEX IF NOT EXISTS idx_reactions_message ON reactions(message_id);
CREATE INDEX IF NOT EXISTS idx_reactions_user ON reactions(user_id);
CREATE INDEX IF NOT EXISTS idx_huddles_channel ON huddles(channel_id);
CREATE INDEX IF NOT EXISTS idx_files_user ON files(user_id);
CREATE INDEX IF NOT EXISTS idx_weekly_stats_lookup ON weekly_stats(relationship_key, week_start);
CREATE INDEX IF NOT EXISTS idx_monthly_stats_lookup ON monthly_stats(relationship_key, month);
"""


class Database:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def initialize(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_user(self, slack_id: str, name: str | None = None,
                     display_name: str | None = None, real_name: str | None = None,
                     is_bot: bool = False, timezone: str | None = None,
                     tz_offset: int | None = None, title: str | None = None,
                     start_date: str | None = None, status_text: str | None = None,
                     status_emoji: str | None = None, locale: str | None = None,
                     avatar_url: str | None = None) -> int:
        self.execute(
            """INSERT INTO users (slack_id, name, display_name, real_name, is_bot,
                   timezone, tz_offset, title, start_date, status_text, status_emoji,
                   locale, avatar_url, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slack_id) DO UPDATE SET
                   name=excluded.name, display_name=excluded.display_name,
                   real_name=excluded.real_name, is_bot=excluded.is_bot,
                   timezone=excluded.timezone, tz_offset=excluded.tz_offset,
                   title=excluded.title, start_date=excluded.start_date,
                   status_text=excluded.status_text, status_emoji=excluded.status_emoji,
                   locale=excluded.locale, avatar_url=excluded.avatar_url,
                   synced_at=excluded.synced_at""",
            (slack_id, name, display_name, real_name, int(is_bot),
             timezone, tz_offset, title, start_date, status_text, status_emoji,
             locale, avatar_url, time.time()),
        )
        self.commit()
        row = self.execute("SELECT id FROM users WHERE slack_id = ?", (slack_id,)).fetchone()
        return row["id"]

    def upsert_channel(self, slack_id: str, name: str | None = None,
                        type: str = "channel", created_at: float | None = None,
                        topic: str | None = None, purpose: str | None = None,
                        num_members: int | None = None, is_archived: bool = False) -> int:
        self.execute(
            """INSERT INTO channels (slack_id, name, type, created_at, topic, purpose,
                   num_members, is_archived, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slack_id) DO UPDATE SET
                   name=excluded.name, type=excluded.type, created_at=excluded.created_at,
                   topic=excluded.topic, purpose=excluded.purpose,
                   num_members=excluded.num_members, is_archived=excluded.is_archived,
                   synced_at=excluded.synced_at""",
            (slack_id, name, type, created_at, topic, purpose,
             num_members, int(is_archived), time.time()),
        )
        self.commit()
        row = self.execute("SELECT id FROM channels WHERE slack_id = ?", (slack_id,)).fetchone()
        return row["id"]

    def upsert_message(self, channel_id: int, user_id: int | None, slack_ts: str,
                        text: str | None = None, created_at: float = 0.0,
                        subtype: str | None = None, thread_ts: str | None = None,
                        reply_count: int = 0, files_count: int = 0) -> int:
        self.execute(
            """INSERT INTO messages (channel_id, user_id, slack_ts, text, subtype,
                   thread_ts, reply_count, files_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(channel_id, slack_ts) DO UPDATE SET
                   text=excluded.text, subtype=excluded.subtype,
                   thread_ts=excluded.thread_ts, reply_count=excluded.reply_count,
                   files_count=excluded.files_count""",
            (channel_id, user_id, slack_ts, text, subtype,
             thread_ts, reply_count, files_count, created_at),
        )
        self.commit()
        row = self.execute(
            "SELECT id FROM messages WHERE channel_id = ? AND slack_ts = ?",
            (channel_id, slack_ts),
        ).fetchone()
        return row["id"]

    def get_user_id(self, slack_id: str) -> int | None:
        row = self.execute("SELECT id FROM users WHERE slack_id = ?", (slack_id,)).fetchone()
        return row["id"] if row else None

    def get_channel_id(self, slack_id: str) -> int | None:
        row = self.execute("SELECT id FROM channels WHERE slack_id = ?", (slack_id,)).fetchone()
        return row["id"] if row else None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/slackwrap/db.py tests/test_db.py tests/conftest.py
git commit -m "feat(v2): add Database class with full schema, upserts, FTS5, indexes"
```

---

### Task 4: Refactor Slack Client

Refactor the existing Slack client to work with the new database. Keep the same rate limiting logic (it's battle-tested) but add new API endpoints and return raw dicts (the sync engine handles DB writes).

**Files:**
- Create: `src/slackwrap/slack_client.py` (new file, not modifying old `src/slack_client.py`)
- Create: `tests/test_slack_client_v2.py`

- [ ] **Step 1: Write failing tests for the new client**

```python
# tests/test_slack_client_v2.py
import json
import pytest
from unittest.mock import patch, MagicMock
from slackwrap.slack_client import SlackClient, RateLimiter


class TestRateLimiter:
    def test_allows_requests_under_limit(self):
        limiter = RateLimiter()
        # Tier 3 allows 45/min
        for _ in range(10):
            limiter.acquire("conversations.history")
        # Should not raise or block significantly

    def test_tracks_endpoint_counts(self):
        limiter = RateLimiter()
        limiter.acquire("conversations.history")
        limiter.acquire("conversations.history")
        assert limiter.get_count("conversations.history") == 2

    def test_different_endpoints_tracked_separately(self):
        limiter = RateLimiter()
        limiter.acquire("conversations.history")
        limiter.acquire("users.list")
        assert limiter.get_count("conversations.history") == 1
        assert limiter.get_count("users.list") == 1


class TestSlackClient:
    def _mock_response(self, data: dict, status_code: int = 200):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = data
        mock.headers = {}
        mock.raise_for_status = MagicMock()
        return mock

    @patch("slackwrap.slack_client.requests.get")
    def test_auth_test(self, mock_get):
        mock_get.return_value = self._mock_response({
            "ok": True,
            "user_id": "U12345",
            "user": "testuser",
            "team": "TestTeam",
            "team_id": "T12345",
        })
        client = SlackClient(token="xoxp-test-token")
        assert client.user_id == "U12345"
        assert client.username == "testuser"
        assert client.team == "TestTeam"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_messages_single_page(self, mock_get):
        auth_resp = self._mock_response({
            "ok": True, "user_id": "U1", "user": "test", "team": "T",
        })
        history_resp = self._mock_response({
            "ok": True,
            "messages": [
                {"ts": "1700000001.000001", "user": "U1", "text": "hello"},
                {"ts": "1700000002.000001", "user": "U2", "text": "world"},
            ],
            "has_more": False,
        })
        mock_get.side_effect = [auth_resp, history_resp]

        client = SlackClient(token="xoxp-test")
        messages = client.fetch_messages("C12345")
        assert len(messages) == 2
        assert messages[0]["text"] == "hello"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_messages_pagination(self, mock_get):
        auth_resp = self._mock_response({
            "ok": True, "user_id": "U1", "user": "test", "team": "T",
        })
        page1 = self._mock_response({
            "ok": True,
            "messages": [{"ts": "1.0", "user": "U1", "text": "a"}],
            "has_more": True,
            "response_metadata": {"next_cursor": "cursor123"},
        })
        page2 = self._mock_response({
            "ok": True,
            "messages": [{"ts": "2.0", "user": "U1", "text": "b"}],
            "has_more": False,
        })
        mock_get.side_effect = [auth_resp, page1, page2]

        client = SlackClient(token="xoxp-test")
        messages = client.fetch_messages("C12345")
        assert len(messages) == 2

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_user_profile(self, mock_get):
        auth_resp = self._mock_response({
            "ok": True, "user_id": "U1", "user": "test", "team": "T",
        })
        profile_resp = self._mock_response({
            "ok": True,
            "profile": {
                "display_name": "Alice",
                "real_name": "Alice Smith",
                "title": "Engineer",
                "fields": {"Xf123": {"value": "2023-01-15", "label": "Start Date"}},
            },
        })
        mock_get.side_effect = [auth_resp, profile_resp]

        client = SlackClient(token="xoxp-test")
        profile = client.fetch_user_profile("U12345")
        assert profile["display_name"] == "Alice"
        assert profile["title"] == "Engineer"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_pins(self, mock_get):
        auth_resp = self._mock_response({
            "ok": True, "user_id": "U1", "user": "test", "team": "T",
        })
        pins_resp = self._mock_response({
            "ok": True,
            "items": [
                {"type": "message", "message": {"ts": "1.0"}, "created_by": "U1", "created": 1700000000},
            ],
        })
        mock_get.side_effect = [auth_resp, pins_resp]

        client = SlackClient(token="xoxp-test")
        pins = client.fetch_pins("C12345")
        assert len(pins) == 1
        assert pins[0]["created_by"] == "U1"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_conversation_info(self, mock_get):
        auth_resp = self._mock_response({
            "ok": True, "user_id": "U1", "user": "test", "team": "T",
        })
        info_resp = self._mock_response({
            "ok": True,
            "channel": {
                "id": "C12345",
                "name": "general",
                "created": 1600000000,
                "topic": {"value": "Discussion"},
                "purpose": {"value": "General chat"},
                "num_members": 42,
            },
        })
        mock_get.side_effect = [auth_resp, info_resp]

        client = SlackClient(token="xoxp-test")
        info = client.fetch_conversation_info("C12345")
        assert info["name"] == "general"
        assert info["num_members"] == 42

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_team_info(self, mock_get):
        auth_resp = self._mock_response({
            "ok": True, "user_id": "U1", "user": "test", "team": "T",
        })
        team_resp = self._mock_response({
            "ok": True,
            "team": {
                "id": "T12345",
                "name": "Acme Corp",
                "domain": "acme",
                "icon": {"image_68": "https://example.com/icon.png"},
            },
        })
        mock_get.side_effect = [auth_resp, team_resp]

        client = SlackClient(token="xoxp-test")
        info = client.fetch_team_info()
        assert info["name"] == "Acme Corp"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_user_conversations(self, mock_get):
        auth_resp = self._mock_response({
            "ok": True, "user_id": "U1", "user": "test", "team": "T",
        })
        convos_resp = self._mock_response({
            "ok": True,
            "channels": [
                {"id": "C1", "name": "general"},
                {"id": "C2", "name": "random"},
            ],
            "response_metadata": {"next_cursor": ""},
        })
        mock_get.side_effect = [auth_resp, convos_resp]

        client = SlackClient(token="xoxp-test")
        channels = client.fetch_user_conversations("U12345")
        assert len(channels) == 2

    @patch("slackwrap.slack_client.requests.get")
    def test_find_shared_channels_uses_intersection(self, mock_get):
        auth_resp = self._mock_response({
            "ok": True, "user_id": "U1", "user": "test", "team": "T",
        })
        my_convos = self._mock_response({
            "ok": True,
            "channels": [{"id": "C1"}, {"id": "C2"}, {"id": "C3"}],
            "response_metadata": {"next_cursor": ""},
        })
        their_convos = self._mock_response({
            "ok": True,
            "channels": [{"id": "C2"}, {"id": "C3"}, {"id": "C4"}],
            "response_metadata": {"next_cursor": ""},
        })
        mock_get.side_effect = [auth_resp, my_convos, their_convos]

        client = SlackClient(token="xoxp-test")
        shared = client.find_shared_channels("U2")
        shared_ids = {ch["id"] for ch in shared}
        assert shared_ids == {"C2", "C3"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_slack_client_v2.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement the new SlackClient**

```python
# src/slackwrap/slack_client.py
import sys
import time
import requests

API_BASE = "https://slack.com/api"

TIER_LIMITS = {
    2: {"max": 18, "label": "Tier 2"},
    3: {"max": 45, "label": "Tier 3"},
    4: {"max": 90, "label": "Tier 4"},
}

ENDPOINT_TIERS = {
    "users.list": 2,
    "users.info": 4,
    "users.profile.get": 4,
    "users.conversations": 3,
    "conversations.list": 2,
    "conversations.history": 3,
    "conversations.replies": 3,
    "conversations.info": 3,
    "conversations.members": 4,
    "auth.test": 4,
    "team.info": 3,
    "files.list": 3,
    "reactions.list": 2,
    "pins.list": 2,
    "bookmarks.list": 3,
    "emoji.list": 2,
    "dnd.info": 3,
    "search.messages": 2,
    "chat.getPermalink": 4,
}


class RateLimiter:
    def __init__(self):
        self._timestamps: dict[str, list[float]] = {}

    def get_count(self, endpoint: str) -> int:
        now = time.time()
        ts = self._timestamps.get(endpoint, [])
        self._timestamps[endpoint] = [t for t in ts if now - t < 60]
        return len(self._timestamps[endpoint])

    def acquire(self, endpoint: str) -> None:
        tier = ENDPOINT_TIERS.get(endpoint, 3)
        max_req = TIER_LIMITS[tier]["max"]
        count = self.get_count(endpoint)

        if count >= max_req:
            ts = self._timestamps.get(endpoint, [])
            if ts:
                wait = 60.0 - (time.time() - ts[0]) + 0.1
                if wait > 0:
                    time.sleep(wait)
            self.get_count(endpoint)

        self._timestamps.setdefault(endpoint, []).append(time.time())

    def budget_estimate(self, calls: dict[str, int]) -> float:
        """Estimate total seconds needed for a set of API calls by endpoint."""
        total = 0.0
        for endpoint, count in calls.items():
            tier = ENDPOINT_TIERS.get(endpoint, 3)
            max_req = TIER_LIMITS[tier]["max"]
            windows = count / max_req
            total += windows * 60
        return total


class SlackClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self._limiter = RateLimiter()
        self.user_id: str = ""
        self.username: str = ""
        self.team: str = ""
        self.team_id: str = ""
        self._authenticate()

    def _authenticate(self) -> None:
        data = self._get("auth.test")
        self.user_id = data["user_id"]
        self.username = data.get("user", "")
        self.team = data.get("team", "")
        self.team_id = data.get("team_id", "")

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        self._limiter.acquire(endpoint)
        resp = requests.get(
            f"{API_BASE}/{endpoint}",
            headers=self.headers,
            params=params or {},
            timeout=30,
        )
        while resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            self._limiter.acquire(endpoint)
            resp = requests.get(
                f"{API_BASE}/{endpoint}",
                headers=self.headers,
                params=params or {},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error ({endpoint}): {data.get('error', 'unknown')}")
        return data

    def _paginate(self, endpoint: str, params: dict, items_key: str = "channels") -> list[dict]:
        results = []
        cursor = ""
        while True:
            p = {**params}
            if cursor:
                p["cursor"] = cursor
            data = self._get(endpoint, p)
            results.extend(data.get(items_key, []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return results

    # --- Users ---

    def fetch_all_users(self) -> list[dict]:
        return self._paginate("users.list", {"limit": 200}, items_key="members")

    def fetch_user_info(self, user_id: str) -> dict:
        data = self._get("users.info", {"user": user_id})
        return data.get("user", {})

    def fetch_user_profile(self, user_id: str) -> dict:
        data = self._get("users.profile.get", {"user": user_id})
        return data.get("profile", {})

    # --- Channels ---

    def fetch_all_channels(self, types: str = "public_channel,private_channel") -> list[dict]:
        return self._paginate(
            "conversations.list",
            {"types": types, "limit": 200, "exclude_archived": "true"},
        )

    def fetch_dm_channels(self) -> list[dict]:
        return self._paginate("conversations.list", {"types": "im", "limit": 200})

    def fetch_conversation_info(self, channel_id: str) -> dict:
        data = self._get("conversations.info", {"channel": channel_id})
        return data.get("channel", {})

    def fetch_user_conversations(self, user_id: str) -> list[dict]:
        return self._paginate(
            "users.conversations",
            {"user": user_id, "types": "public_channel,private_channel", "limit": 200},
        )

    def find_shared_channels(self, target_user_id: str) -> list[dict]:
        my_channels = self.fetch_user_conversations(self.user_id)
        their_channels = self.fetch_user_conversations(target_user_id)
        their_ids = {ch["id"] for ch in their_channels}
        return [ch for ch in my_channels if ch["id"] in their_ids]

    # --- Messages ---

    def fetch_messages(self, channel_id: str, oldest: str | None = None) -> list[dict]:
        messages = []
        cursor = ""
        while True:
            params: dict = {"channel": channel_id, "limit": 999}
            if oldest:
                params["oldest"] = oldest
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.history", params)
            messages.extend(data.get("messages", []))
            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return messages

    def fetch_thread_replies(self, channel_id: str, thread_ts: str) -> list[dict]:
        replies = []
        cursor = ""
        while True:
            params: dict = {"channel": channel_id, "ts": thread_ts, "limit": 999}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.replies", params)
            replies.extend(data.get("messages", []))
            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return replies

    def fetch_messages_with_threads(self, channel_id: str, oldest: str | None = None) -> list[dict]:
        messages = self.fetch_messages(channel_id, oldest=oldest)
        thread_parents = [m for m in messages if m.get("reply_count", 0) > 0]
        existing_ts = {m["ts"] for m in messages}
        for parent in thread_parents:
            replies = self.fetch_thread_replies(channel_id, parent["ts"])
            for reply in replies:
                if reply["ts"] not in existing_ts:
                    messages.append(reply)
                    existing_ts.add(reply["ts"])
        return messages

    # --- Reactions ---

    def fetch_reactions_for_user(self, user_id: str) -> list[dict]:
        return self._paginate(
            "reactions.list",
            {"user": user_id, "limit": 200, "full": "true"},
            items_key="items",
        )

    # --- Files ---

    def fetch_files(self, channel: str | None = None, user: str | None = None) -> list[dict]:
        params: dict = {"count": 100}
        if channel:
            params["channel"] = channel
        if user:
            params["user"] = user
        return self._paginate("files.list", params, items_key="files")

    # --- Pins ---

    def fetch_pins(self, channel_id: str) -> list[dict]:
        data = self._get("pins.list", {"channel": channel_id})
        return data.get("items", [])

    # --- Team ---

    def fetch_team_info(self) -> dict:
        data = self._get("team.info")
        return data.get("team", {})

    # --- Emoji ---

    def fetch_custom_emoji(self) -> dict[str, str]:
        data = self._get("emoji.list")
        return data.get("emoji", {})

    # --- DND ---

    def fetch_dnd_info(self, user_id: str) -> dict:
        return self._get("dnd.info", {"user": user_id})

    # --- Search ---

    def search_messages(self, query: str) -> list[dict]:
        messages = []
        page = 1
        while True:
            data = self._get("search.messages", {"query": query, "count": 100, "page": page})
            matches = data.get("messages", {}).get("matches", [])
            messages.extend(matches)
            total = data.get("messages", {}).get("total", 0)
            if len(messages) >= total:
                break
            page += 1
        return messages

    # --- Permalinks ---

    def get_permalink(self, channel_id: str, message_ts: str) -> str:
        data = self._get("chat.getPermalink", {"channel": channel_id, "message_ts": message_ts})
        return data.get("permalink", "")

    # --- User Search (for TUI type-ahead) ---

    def search_users(self, query: str) -> list[dict]:
        query_lower = query.lower()
        all_users = self.fetch_all_users()
        matches = []
        for member in all_users:
            if member.get("deleted") or member.get("is_bot"):
                continue
            searchable = " ".join([
                member.get("real_name", ""),
                member.get("name", ""),
                member.get("profile", {}).get("display_name", ""),
            ]).lower()
            if query_lower in searchable:
                matches.append(member)
        return matches
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_slack_client_v2.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/slack_client.py tests/test_slack_client_v2.py
git commit -m "feat(v2): add new SlackClient with all API endpoints, rate limiter, efficient shared channel discovery"
```

---

### Task 5: Sync Engine

The sync engine orchestrates fetching from Slack and writing into SQLite. It handles initial sync, delta sync, and is resumable.

**Files:**
- Create: `src/slackwrap/sync.py`
- Create: `tests/test_sync.py`

- [ ] **Step 1: Write failing tests for sync engine**

```python
# tests/test_sync.py
import json
import time
import pytest
from unittest.mock import MagicMock, patch
from slackwrap.db import Database
from slackwrap.sync import SyncEngine


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.user_id = "U_ME"
    client.username = "testuser"
    client.team = "TestTeam"
    client.team_id = "T123"
    return client


@pytest.fixture
def sync_engine(db, mock_client):
    return SyncEngine(db=db, client=mock_client)


class TestSyncUsers:
    def test_sync_stores_user_in_db(self, sync_engine, mock_client, db):
        mock_client.fetch_user_info.return_value = {
            "id": "U1",
            "name": "alice",
            "real_name": "Alice Smith",
            "profile": {"display_name": "alice"},
            "is_bot": False,
            "tz": "America/New_York",
            "tz_offset": -18000,
            "locale": "en-US",
        }
        mock_client.fetch_user_profile.return_value = {
            "title": "Engineer",
            "fields": {},
        }
        sync_engine.sync_user("U1")

        row = db.execute("SELECT * FROM users WHERE slack_id = ?", ("U1",)).fetchone()
        assert row is not None
        assert row["real_name"] == "Alice Smith"
        assert row["timezone"] == "America/New_York"
        assert row["title"] == "Engineer"

    def test_sync_user_updates_existing(self, sync_engine, mock_client, db):
        mock_client.fetch_user_info.return_value = {
            "id": "U1", "name": "alice", "real_name": "Alice Old",
            "profile": {"display_name": "alice"}, "is_bot": False,
        }
        mock_client.fetch_user_profile.return_value = {"title": "Junior"}
        sync_engine.sync_user("U1")

        mock_client.fetch_user_info.return_value["real_name"] = "Alice New"
        mock_client.fetch_user_profile.return_value["title"] = "Senior"
        sync_engine.sync_user("U1")

        rows = db.execute("SELECT * FROM users WHERE slack_id = ?", ("U1",)).fetchall()
        assert len(rows) == 1
        assert rows[0]["real_name"] == "Alice New"
        assert rows[0]["title"] == "Senior"


class TestSyncMessages:
    def test_initial_sync_stores_messages(self, sync_engine, mock_client, db):
        db.upsert_channel(slack_id="C1", name="general", type="channel")
        db.upsert_user(slack_id="U1", name="alice")

        mock_client.fetch_messages_with_threads.return_value = [
            {"ts": "1700000001.000001", "user": "U1", "text": "hello"},
            {"ts": "1700000002.000001", "user": "U1", "text": "world"},
        ]

        sync_engine.sync_channel_messages("C1")

        count = db.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
        assert count == 2

    def test_delta_sync_only_fetches_new(self, sync_engine, mock_client, db):
        ch_id = db.upsert_channel(slack_id="C1", name="general", type="channel")
        db.upsert_user(slack_id="U1", name="alice")

        # Set sync state as if we already synced up to ts 1700000002
        db.execute(
            "INSERT INTO sync_state (channel_id, last_synced_ts, last_synced_at, status) VALUES (?, ?, ?, ?)",
            (ch_id, "1700000002.000001", time.time(), "complete"),
        )
        db.commit()

        mock_client.fetch_messages_with_threads.return_value = [
            {"ts": "1700000003.000001", "user": "U1", "text": "new message"},
        ]

        sync_engine.sync_channel_messages("C1")

        # Verify fetch was called with oldest parameter
        call_args = mock_client.fetch_messages_with_threads.call_args
        assert call_args[1].get("oldest") == "1700000002.000001" or call_args[0][1] == "1700000002.000001"

    def test_sync_extracts_reactions(self, sync_engine, mock_client, db):
        db.upsert_channel(slack_id="C1", name="general", type="channel")
        db.upsert_user(slack_id="U1", name="alice")
        db.upsert_user(slack_id="U2", name="bob")

        mock_client.fetch_messages_with_threads.return_value = [
            {
                "ts": "1700000001.000001", "user": "U1", "text": "hello",
                "reactions": [
                    {"name": "thumbsup", "users": ["U2"], "count": 1},
                ],
            },
        ]

        sync_engine.sync_channel_messages("C1")

        reactions = db.execute("SELECT * FROM reactions").fetchall()
        assert len(reactions) == 1
        assert reactions[0]["emoji_name"] == "thumbsup"

    def test_sync_extracts_huddles(self, sync_engine, mock_client, db):
        db.upsert_channel(slack_id="C1", name="general", type="channel")
        db.upsert_user(slack_id="U1", name="alice")
        db.upsert_user(slack_id="U2", name="bob")

        mock_client.fetch_messages_with_threads.return_value = [
            {
                "ts": "1700000001.000001",
                "user": "U1",
                "text": "",
                "subtype": "huddle_thread",
                "room": {
                    "date_start": 1700000000,
                    "date_end": 1700003600,
                    "has_ended": True,
                    "participant_history": ["U1", "U2"],
                    "created_by": "U1",
                },
            },
        ]

        sync_engine.sync_channel_messages("C1")

        huddles = db.execute("SELECT * FROM huddles").fetchall()
        assert len(huddles) == 1
        assert huddles[0]["duration_seconds"] == 3600
        assert json.loads(huddles[0]["participant_ids"]) == ["U1", "U2"]


class TestSyncPins:
    def test_sync_pins(self, sync_engine, mock_client, db):
        db.upsert_channel(slack_id="C1", name="general", type="channel")
        db.upsert_user(slack_id="U1", name="alice")

        mock_client.fetch_pins.return_value = [
            {"type": "message", "message": {"ts": "1.0"}, "created_by": "U1", "created": 1700000000},
        ]

        sync_engine.sync_channel_pins("C1")

        pins = db.execute("SELECT * FROM pins").fetchall()
        assert len(pins) == 1


class TestSyncState:
    def test_sync_updates_sync_state(self, sync_engine, mock_client, db):
        db.upsert_channel(slack_id="C1", name="general", type="channel")
        db.upsert_user(slack_id="U1", name="alice")

        mock_client.fetch_messages_with_threads.return_value = [
            {"ts": "1700000001.000001", "user": "U1", "text": "hello"},
            {"ts": "1700000005.000001", "user": "U1", "text": "latest"},
        ]

        sync_engine.sync_channel_messages("C1")

        ch_id = db.get_channel_id("C1")
        state = db.execute("SELECT * FROM sync_state WHERE channel_id = ?", (ch_id,)).fetchone()
        assert state is not None
        assert state["last_synced_ts"] == "1700000005.000001"
        assert state["status"] == "complete"

    def test_sync_is_resumable(self, sync_engine, mock_client, db):
        ch_id = db.upsert_channel(slack_id="C1", name="general", type="channel")
        db.upsert_user(slack_id="U1", name="alice")

        # Mark as errored mid-sync
        db.execute(
            "INSERT INTO sync_state (channel_id, last_synced_ts, last_synced_at, status) VALUES (?, ?, ?, ?)",
            (ch_id, "1700000003.000001", time.time(), "error"),
        )
        db.commit()

        mock_client.fetch_messages_with_threads.return_value = [
            {"ts": "1700000004.000001", "user": "U1", "text": "after error"},
        ]

        sync_engine.sync_channel_messages("C1")

        state = db.execute("SELECT * FROM sync_state WHERE channel_id = ?", (ch_id,)).fetchone()
        assert state["status"] == "complete"
        assert state["last_synced_ts"] == "1700000004.000001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sync.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement the SyncEngine**

```python
# src/slackwrap/sync.py
import json
import time
from slackwrap.db import Database
from slackwrap.slack_client import SlackClient


class SyncEngine:
    def __init__(self, db: Database, client: SlackClient):
        self.db = db
        self.client = client

    # --- User Sync ---

    def sync_user(self, slack_id: str) -> int:
        info = self.client.fetch_user_info(slack_id)
        profile = self.client.fetch_user_profile(slack_id)
        return self.db.upsert_user(
            slack_id=info.get("id", slack_id),
            name=info.get("name"),
            display_name=info.get("profile", {}).get("display_name"),
            real_name=info.get("real_name"),
            is_bot=info.get("is_bot", False),
            timezone=info.get("tz"),
            tz_offset=info.get("tz_offset"),
            title=profile.get("title"),
            start_date=self._extract_start_date(profile),
            status_text=profile.get("status_text"),
            status_emoji=profile.get("status_emoji"),
            locale=info.get("locale"),
            avatar_url=info.get("profile", {}).get("image_72"),
        )

    def _extract_start_date(self, profile: dict) -> str | None:
        fields = profile.get("fields") or {}
        for field_id, field_data in fields.items():
            label = (field_data.get("label") or "").lower()
            if "start" in label and "date" in label:
                return field_data.get("value")
        return None

    # --- Channel Sync ---

    def sync_channel(self, slack_id: str) -> int:
        info = self.client.fetch_conversation_info(slack_id)
        return self.db.upsert_channel(
            slack_id=info.get("id", slack_id),
            name=info.get("name"),
            type=self._channel_type(info),
            created_at=info.get("created"),
            topic=info.get("topic", {}).get("value") if isinstance(info.get("topic"), dict) else info.get("topic"),
            purpose=info.get("purpose", {}).get("value") if isinstance(info.get("purpose"), dict) else info.get("purpose"),
            num_members=info.get("num_members"),
            is_archived=info.get("is_archived", False),
        )

    def _channel_type(self, info: dict) -> str:
        if info.get("is_im"):
            return "dm"
        if info.get("is_mpim"):
            return "mpim"
        if info.get("is_group") or info.get("is_private"):
            return "group"
        return "channel"

    # --- Message Sync ---

    def sync_channel_messages(self, channel_slack_id: str) -> int:
        ch_id = self.db.get_channel_id(channel_slack_id)
        if ch_id is None:
            ch_id = self.db.upsert_channel(slack_id=channel_slack_id)

        # Check sync state for delta sync
        state = self.db.execute(
            "SELECT * FROM sync_state WHERE channel_id = ?", (ch_id,)
        ).fetchone()
        oldest = None
        if state and state["last_synced_ts"]:
            oldest = state["last_synced_ts"]

        # Mark as syncing
        self.db.execute(
            """INSERT INTO sync_state (channel_id, status) VALUES (?, 'syncing')
               ON CONFLICT(channel_id) DO UPDATE SET status='syncing'""",
            (ch_id,),
        )
        self.db.commit()

        # Fetch messages
        if oldest:
            raw_messages = self.client.fetch_messages_with_threads(channel_slack_id, oldest=oldest)
        else:
            raw_messages = self.client.fetch_messages_with_threads(channel_slack_id)

        count = 0
        latest_ts = oldest or ""

        for msg in raw_messages:
            ts = msg.get("ts", "")
            user_slack_id = msg.get("user")

            # Ensure user exists in DB
            user_id = None
            if user_slack_id:
                user_id = self.db.get_user_id(user_slack_id)
                if user_id is None:
                    user_id = self.db.upsert_user(slack_id=user_slack_id, name=user_slack_id)

            # Upsert message
            msg_id = self.db.upsert_message(
                channel_id=ch_id,
                user_id=user_id,
                slack_ts=ts,
                text=msg.get("text", ""),
                created_at=float(ts.split(".")[0]) if ts else 0.0,
                subtype=msg.get("subtype"),
                thread_ts=msg.get("thread_ts"),
                reply_count=msg.get("reply_count", 0),
                files_count=len(msg.get("files", [])),
            )

            # Extract reactions
            for reaction in msg.get("reactions", []):
                emoji_name = reaction.get("name", "")
                for uid in reaction.get("users", []):
                    r_user_id = self.db.get_user_id(uid)
                    if r_user_id is None:
                        r_user_id = self.db.upsert_user(slack_id=uid, name=uid)
                    self.db.execute(
                        "INSERT OR IGNORE INTO reactions (message_id, user_id, emoji_name) VALUES (?, ?, ?)",
                        (msg_id, r_user_id, emoji_name),
                    )

            # Extract huddles
            if msg.get("subtype") == "huddle_thread":
                room = msg.get("room", {})
                if room.get("has_ended"):
                    created_by = room.get("created_by")
                    created_by_id = None
                    if created_by:
                        created_by_id = self.db.get_user_id(created_by)
                        if created_by_id is None:
                            created_by_id = self.db.upsert_user(slack_id=created_by, name=created_by)

                    participants = room.get("participant_history", [])
                    started = room.get("date_start", 0)
                    ended = room.get("date_end", 0)
                    duration = int(ended - started)

                    self.db.execute(
                        """INSERT OR IGNORE INTO huddles
                           (channel_id, created_by_user_id, started_at, ended_at, duration_seconds, participant_ids)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (ch_id, created_by_id, started, ended, duration, json.dumps(participants)),
                    )

            if ts > latest_ts:
                latest_ts = ts
            count += 1

        # Update sync state
        self.db.execute(
            """INSERT INTO sync_state (channel_id, last_synced_ts, last_synced_at, status)
               VALUES (?, ?, ?, 'complete')
               ON CONFLICT(channel_id) DO UPDATE SET
                   last_synced_ts=excluded.last_synced_ts,
                   last_synced_at=excluded.last_synced_at,
                   status='complete'""",
            (ch_id, latest_ts, time.time()),
        )
        self.db.commit()
        return count

    # --- Pins Sync ---

    def sync_channel_pins(self, channel_slack_id: str) -> int:
        ch_id = self.db.get_channel_id(channel_slack_id)
        if ch_id is None:
            ch_id = self.db.upsert_channel(slack_id=channel_slack_id)

        pins = self.client.fetch_pins(channel_slack_id)
        count = 0
        for pin in pins:
            if pin.get("type") != "message":
                continue
            user_slack_id = pin.get("created_by")
            user_id = None
            if user_slack_id:
                user_id = self.db.get_user_id(user_slack_id)
                if user_id is None:
                    user_id = self.db.upsert_user(slack_id=user_slack_id, name=user_slack_id)

            msg_ts = pin.get("message", {}).get("ts")
            self.db.execute(
                "INSERT OR IGNORE INTO pins (channel_id, user_id, message_ts, pinned_at) VALUES (?, ?, ?, ?)",
                (ch_id, user_id, msg_ts, pin.get("created")),
            )
            count += 1
        self.db.commit()
        return count

    # --- Files Sync ---

    def sync_channel_files(self, channel_slack_id: str) -> int:
        ch_id = self.db.get_channel_id(channel_slack_id)
        if ch_id is None:
            ch_id = self.db.upsert_channel(slack_id=channel_slack_id)

        files = self.client.fetch_files(channel=channel_slack_id)
        count = 0
        for f in files:
            user_slack_id = f.get("user")
            user_id = None
            if user_slack_id:
                user_id = self.db.get_user_id(user_slack_id)
                if user_id is None:
                    user_id = self.db.upsert_user(slack_id=user_slack_id, name=user_slack_id)

            self.db.execute(
                """INSERT OR IGNORE INTO files
                   (channel_id, user_id, slack_file_id, name, filetype, size_bytes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (ch_id, user_id, f.get("id", ""), f.get("name"), f.get("filetype"),
                 f.get("size"), f.get("created")),
            )
            count += 1
        self.db.commit()
        return count

    # --- Full Relationship Sync ---

    def sync_relationship(self, target_user_slack_id: str, include_shared_channels: bool = True) -> dict:
        """Full sync for a relationship: DM + optionally shared channels."""
        results = {"users": 0, "channels": 0, "messages": 0, "pins": 0, "files": 0}

        # Sync both users
        self.sync_user(self.client.user_id)
        self.sync_user(target_user_slack_id)
        results["users"] = 2

        # Find the DM channel
        dm_channels = self.client.fetch_dm_channels()
        dm_channel = None
        for ch in dm_channels:
            if ch.get("user") == target_user_slack_id:
                dm_channel = ch
                break

        channels_to_sync = []
        if dm_channel:
            self.sync_channel(dm_channel["id"])
            channels_to_sync.append(dm_channel["id"])

        # Find shared channels
        if include_shared_channels:
            shared = self.client.find_shared_channels(target_user_slack_id)
            for ch in shared:
                self.sync_channel(ch["id"])
                channels_to_sync.append(ch["id"])

        results["channels"] = len(channels_to_sync)

        # Sync messages, pins, files for each channel
        for ch_id in channels_to_sync:
            results["messages"] += self.sync_channel_messages(ch_id)
            results["pins"] += self.sync_channel_pins(ch_id)
            results["files"] += self.sync_channel_files(ch_id)

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sync.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/sync.py tests/test_sync.py
git commit -m "feat(v2): add SyncEngine — initial sync, delta sync, resumable, extracts reactions/huddles/pins/files"
```

---

### Task 6: FTS5 Sync Triggers

FTS5 needs triggers to stay in sync with the messages table when messages are inserted or updated.

**Files:**
- Modify: `src/slackwrap/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing test for FTS**

Add to `tests/test_db.py`:

```python
def test_fts_search_finds_message(db):
    db.upsert_channel(slack_id="C1", name="general", type="channel")
    db.upsert_user(slack_id="U1", name="alice")

    ch_id = db.get_channel_id("C1")
    u_id = db.get_user_id("U1")

    db.upsert_message(channel_id=ch_id, user_id=u_id, slack_ts="1.0",
                       text="let's discuss the deployment plan", created_at=1700000000.0)
    db.upsert_message(channel_id=ch_id, user_id=u_id, slack_ts="2.0",
                       text="the weather is nice today", created_at=1700000001.0)

    results = db.execute(
        "SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?", ("deployment",)
    ).fetchall()
    assert len(results) == 1


def test_fts_updated_on_message_update(db):
    db.upsert_channel(slack_id="C1", name="general", type="channel")
    db.upsert_user(slack_id="U1", name="alice")

    ch_id = db.get_channel_id("C1")
    u_id = db.get_user_id("U1")

    db.upsert_message(channel_id=ch_id, user_id=u_id, slack_ts="1.0",
                       text="original text about cats", created_at=1700000000.0)

    # Update the message text
    db.upsert_message(channel_id=ch_id, user_id=u_id, slack_ts="1.0",
                       text="edited text about dogs", created_at=1700000000.0)

    cats = db.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?", ("cats",)).fetchall()
    dogs = db.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?", ("dogs",)).fetchall()
    assert len(cats) == 0
    assert len(dogs) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py::test_fts_search_finds_message tests/test_db.py::test_fts_updated_on_message_update -v`
Expected: FAIL — FTS table is empty because no triggers populate it

- [ ] **Step 3: Add FTS triggers to schema**

Add the following to the end of `SCHEMA_SQL` in `src/slackwrap/db.py`, after the `CREATE VIRTUAL TABLE` and before the `CREATE INDEX` statements:

```sql
CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE OF text ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: All tests PASS (including the two new FTS tests)

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/db.py tests/test_db.py
git commit -m "feat(v2): add FTS5 triggers for automatic full-text index sync"
```

---

### Task 7: Database Helper — Bulk Operations

The sync engine inserts many messages per sync. Adding bulk insert methods avoids per-row commit overhead.

**Files:**
- Modify: `src/slackwrap/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for bulk operations**

Add to `tests/test_db.py`:

```python
def test_bulk_upsert_messages(db):
    ch_id = db.upsert_channel(slack_id="C1", name="general", type="channel")
    u_id = db.upsert_user(slack_id="U1", name="alice")

    messages = [
        {"channel_id": ch_id, "user_id": u_id, "slack_ts": f"{i}.0",
         "text": f"msg {i}", "created_at": 1700000000.0 + i}
        for i in range(100)
    ]
    db.bulk_upsert_messages(messages)

    count = db.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
    assert count == 100

    # FTS should also have all 100
    fts_count = db.execute("SELECT COUNT(*) as c FROM messages_fts").fetchone()["c"]
    assert fts_count == 100


def test_bulk_insert_reactions(db):
    ch_id = db.upsert_channel(slack_id="C1", name="general", type="channel")
    u_id = db.upsert_user(slack_id="U1", name="alice")
    msg_id = db.upsert_message(channel_id=ch_id, user_id=u_id, slack_ts="1.0",
                                text="hello", created_at=1700000000.0)

    reactions = [
        {"message_id": msg_id, "user_id": u_id, "emoji_name": f"emoji_{i}"}
        for i in range(10)
    ]
    db.bulk_insert_reactions(reactions)

    count = db.execute("SELECT COUNT(*) as c FROM reactions").fetchone()["c"]
    assert count == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py::test_bulk_upsert_messages tests/test_db.py::test_bulk_insert_reactions -v`
Expected: FAIL — `AttributeError: 'Database' object has no attribute 'bulk_upsert_messages'`

- [ ] **Step 3: Implement bulk methods**

Add to `Database` class in `src/slackwrap/db.py`:

```python
    def bulk_upsert_messages(self, messages: list[dict]) -> None:
        self.conn.executemany(
            """INSERT INTO messages (channel_id, user_id, slack_ts, text, subtype,
                   thread_ts, reply_count, files_count, created_at)
               VALUES (:channel_id, :user_id, :slack_ts, :text, :subtype,
                   :thread_ts, :reply_count, :files_count, :created_at)
               ON CONFLICT(channel_id, slack_ts) DO UPDATE SET
                   text=excluded.text, subtype=excluded.subtype,
                   thread_ts=excluded.thread_ts, reply_count=excluded.reply_count,
                   files_count=excluded.files_count""",
            [
                {
                    "channel_id": m["channel_id"],
                    "user_id": m.get("user_id"),
                    "slack_ts": m["slack_ts"],
                    "text": m.get("text"),
                    "subtype": m.get("subtype"),
                    "thread_ts": m.get("thread_ts"),
                    "reply_count": m.get("reply_count", 0),
                    "files_count": m.get("files_count", 0),
                    "created_at": m.get("created_at", 0.0),
                }
                for m in messages
            ],
        )
        self.commit()

    def bulk_insert_reactions(self, reactions: list[dict]) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO reactions (message_id, user_id, emoji_name) VALUES (:message_id, :user_id, :emoji_name)",
            reactions,
        )
        self.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/db.py tests/test_db.py
git commit -m "feat(v2): add bulk upsert/insert for messages and reactions"
```

---

### Task 8: Integration Test — Full Sync Flow

End-to-end test that verifies the sync engine writes correct data through the full pipeline.

**Files:**
- Create: `tests/test_sync_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_sync_integration.py
import json
import pytest
from unittest.mock import MagicMock
from slackwrap.db import Database
from slackwrap.sync import SyncEngine


@pytest.fixture
def full_mock_client():
    client = MagicMock()
    client.user_id = "U_ME"
    client.username = "myself"
    client.team = "TestCorp"
    client.team_id = "T1"

    # Auth user info
    def user_info(uid):
        users = {
            "U_ME": {"id": "U_ME", "name": "myself", "real_name": "My Self",
                     "profile": {"display_name": "me"}, "is_bot": False,
                     "tz": "America/Chicago", "tz_offset": -21600},
            "U_THEM": {"id": "U_THEM", "name": "colleague", "real_name": "My Colleague",
                       "profile": {"display_name": "colleague"}, "is_bot": False,
                       "tz": "Europe/London", "tz_offset": 0},
        }
        return users.get(uid, {"id": uid, "name": uid, "profile": {}, "is_bot": False})

    def user_profile(uid):
        profiles = {
            "U_ME": {"title": "Engineer", "fields": {}},
            "U_THEM": {"title": "Designer", "fields": {}},
        }
        return profiles.get(uid, {"title": "", "fields": {}})

    client.fetch_user_info.side_effect = user_info
    client.fetch_user_profile.side_effect = user_profile

    # DM channel
    client.fetch_dm_channels.return_value = [{"id": "D1", "user": "U_THEM"}]

    # Conversation info
    client.fetch_conversation_info.return_value = {
        "id": "D1", "is_im": True, "name": "", "created": 1680000000,
        "topic": {"value": ""}, "purpose": {"value": ""},
    }

    # No shared channels for simplicity
    client.find_shared_channels.return_value = []

    # Messages with variety
    client.fetch_messages_with_threads.return_value = [
        {"ts": "1700000001.000001", "user": "U_ME", "text": "Hey, check this out :rocket:"},
        {"ts": "1700000002.000001", "user": "U_THEM", "text": "Looks great!",
         "reactions": [{"name": "thumbsup", "users": ["U_ME"], "count": 1}]},
        {"ts": "1700000003.000001", "user": "U_ME", "text": "Let's hop on a huddle"},
        {"ts": "1700000004.000001", "user": "U_THEM", "text": "Sure thing",
         "thread_ts": "1700000003.000001"},
        {"ts": "1700000005.000001", "user": "U_ME", "text": "",
         "subtype": "huddle_thread",
         "room": {
             "date_start": 1700000100, "date_end": 1700003700,
             "has_ended": True, "participant_history": ["U_ME", "U_THEM"],
             "created_by": "U_ME",
         }},
    ]

    # Pins
    client.fetch_pins.return_value = [
        {"type": "message", "message": {"ts": "1700000002.000001"},
         "created_by": "U_ME", "created": 1700000010},
    ]

    # Files
    client.fetch_files.return_value = []

    return client


def test_full_sync_relationship(db, full_mock_client):
    engine = SyncEngine(db=db, client=full_mock_client)
    results = engine.sync_relationship("U_THEM", include_shared_channels=False)

    # Check users
    assert results["users"] == 2
    me = db.execute("SELECT * FROM users WHERE slack_id = ?", ("U_ME",)).fetchone()
    assert me["real_name"] == "My Self"
    assert me["timezone"] == "America/Chicago"
    assert me["title"] == "Engineer"

    them = db.execute("SELECT * FROM users WHERE slack_id = ?", ("U_THEM",)).fetchone()
    assert them["real_name"] == "My Colleague"
    assert them["timezone"] == "Europe/London"
    assert them["title"] == "Designer"

    # Check channel
    assert results["channels"] == 1

    # Check messages (5 total: 3 regular + 1 thread reply + 1 huddle_thread)
    msg_count = db.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
    assert msg_count == 5

    # Check reactions
    reaction_count = db.execute("SELECT COUNT(*) as c FROM reactions").fetchone()["c"]
    assert reaction_count == 1
    reaction = db.execute("SELECT * FROM reactions").fetchone()
    assert reaction["emoji_name"] == "thumbsup"

    # Check huddle
    huddle_count = db.execute("SELECT COUNT(*) as c FROM huddles").fetchone()["c"]
    assert huddle_count == 1
    huddle = db.execute("SELECT * FROM huddles").fetchone()
    assert huddle["duration_seconds"] == 3600
    assert json.loads(huddle["participant_ids"]) == ["U_ME", "U_THEM"]

    # Check pins
    pin_count = db.execute("SELECT COUNT(*) as c FROM pins").fetchone()["c"]
    assert pin_count == 1

    # Check sync state
    ch_id = db.get_channel_id("D1")
    state = db.execute("SELECT * FROM sync_state WHERE channel_id = ?", (ch_id,)).fetchone()
    assert state["status"] == "complete"
    assert state["last_synced_ts"] == "1700000005.000001"

    # Check FTS works
    fts_results = db.execute(
        "SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?", ("rocket",)
    ).fetchall()
    assert len(fts_results) == 1


def test_delta_sync_only_adds_new(db, full_mock_client):
    engine = SyncEngine(db=db, client=full_mock_client)

    # Initial sync
    engine.sync_relationship("U_THEM", include_shared_channels=False)
    initial_count = db.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]

    # Delta sync — return only new message
    full_mock_client.fetch_messages_with_threads.return_value = [
        {"ts": "1700000006.000001", "user": "U_THEM", "text": "One more thing"},
    ]

    engine.sync_channel_messages("D1")
    new_count = db.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
    assert new_count == initial_count + 1
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/test_sync_integration.py -v`
Expected: All 2 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests across all test files PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_sync_integration.py
git commit -m "test(v2): add integration tests for full sync flow and delta sync"
```

---

### Task 9: Update pyproject.toml Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update dependencies for Plan 1 completion**

```toml
[project]
name = "slackwrap"
version = "2.0.0"
description = "Your Slack year in review — huddle and message analytics"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
dependencies = [
    "requests>=2.31.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[project.scripts]
slackwrap = "slackwrap.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 2: Verify all tests pass with updated config**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(v2): update pyproject.toml — version 2.0.0, pytest pythonpath config"
```

---

## Plan Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Config — data dir, DB path | 4 tests |
| 2 | Domain models — User, Channel, Message, Huddle, Reaction, File, Pin, SyncState | 8 tests |
| 3 | Database — schema, upserts, FTS5, indexes | 8 tests |
| 4 | Slack Client — all API endpoints, rate limiter, shared channel discovery | 10 tests |
| 5 | Sync Engine — initial sync, delta sync, resumable, extracts reactions/huddles/pins/files | 8 tests |
| 6 | FTS5 triggers — automatic full-text index sync | 2 tests |
| 7 | Bulk operations — fast batch inserts | 2 tests |
| 8 | Integration test — full sync flow end-to-end | 2 tests |
| 9 | pyproject.toml — updated deps and config | 0 (verification only) |

**Total: 9 tasks, 44 tests, ~9 commits**

After this plan, the data layer is complete: SQLite schema, full Slack API client with all new endpoints, sync engine with delta sync support, FTS5 for text search, and comprehensive test coverage. Plan 2 (Analytics Engine) builds on top of this.
