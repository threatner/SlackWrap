from __future__ import annotations

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
    emoji_name TEXT NOT NULL,
    UNIQUE(message_id, user_id, emoji_name)
);

CREATE TABLE IF NOT EXISTS huddles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    created_by_user_id INTEGER REFERENCES users(id),
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL,
    duration_seconds INTEGER,
    participant_ids TEXT NOT NULL DEFAULT '[]',
    UNIQUE(channel_id, started_at, ended_at)
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
    pinned_at REAL,
    UNIQUE(channel_id, message_ts)
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

    def upsert_user(
        self,
        slack_id: str,
        name: str | None = None,
        display_name: str | None = None,
        real_name: str | None = None,
        is_bot: bool = False,
        timezone: str | None = None,
        tz_offset: int | None = None,
        title: str | None = None,
        start_date: str | None = None,
        status_text: str | None = None,
        status_emoji: str | None = None,
        locale: str | None = None,
        avatar_url: str | None = None,
    ) -> int:
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
            (
                slack_id, name, display_name, real_name, int(is_bot),
                timezone, tz_offset, title, start_date, status_text, status_emoji,
                locale, avatar_url, time.time(),
            ),
        )
        row = self.execute(
            "SELECT id FROM users WHERE slack_id = ?", (slack_id,)
        ).fetchone()
        return row["id"]

    def upsert_channel(
        self,
        slack_id: str,
        name: str | None = None,
        type: str = "channel",
        created_at: float | None = None,
        topic: str | None = None,
        purpose: str | None = None,
        num_members: int | None = None,
        is_archived: bool = False,
    ) -> int:
        self.execute(
            """INSERT INTO channels (slack_id, name, type, created_at, topic, purpose,
                   num_members, is_archived, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slack_id) DO UPDATE SET
                   name=excluded.name, type=excluded.type, created_at=excluded.created_at,
                   topic=excluded.topic, purpose=excluded.purpose,
                   num_members=excluded.num_members, is_archived=excluded.is_archived,
                   synced_at=excluded.synced_at""",
            (
                slack_id, name, type, created_at, topic, purpose,
                num_members, int(is_archived), time.time(),
            ),
        )
        row = self.execute(
            "SELECT id FROM channels WHERE slack_id = ?", (slack_id,)
        ).fetchone()
        return row["id"]

    def upsert_message(
        self,
        channel_id: int,
        user_id: int | None,
        slack_ts: str,
        text: str | None = None,
        created_at: float = 0.0,
        subtype: str | None = None,
        thread_ts: str | None = None,
        reply_count: int = 0,
        files_count: int = 0,
    ) -> int:
        self.execute(
            """INSERT INTO messages (channel_id, user_id, slack_ts, text, subtype,
                   thread_ts, reply_count, files_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(channel_id, slack_ts) DO UPDATE SET
                   text=excluded.text, subtype=excluded.subtype,
                   thread_ts=excluded.thread_ts, reply_count=excluded.reply_count,
                   files_count=excluded.files_count""",
            (
                channel_id, user_id, slack_ts, text, subtype,
                thread_ts, reply_count, files_count, created_at,
            ),
        )
        row = self.execute(
            "SELECT id FROM messages WHERE channel_id = ? AND slack_ts = ?",
            (channel_id, slack_ts),
        ).fetchone()
        return row["id"]

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

    def get_user_id(self, slack_id: str) -> int | None:
        row = self.execute(
            "SELECT id FROM users WHERE slack_id = ?", (slack_id,)
        ).fetchone()
        return row["id"] if row else None

    def get_channel_id(self, slack_id: str) -> int | None:
        row = self.execute(
            "SELECT id FROM channels WHERE slack_id = ?", (slack_id,)
        ).fetchone()
        return row["id"] if row else None
