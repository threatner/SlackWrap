from __future__ import annotations
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
            "id": "U1", "name": "alice", "real_name": "Alice Smith",
            "profile": {"display_name": "alice"}, "is_bot": False,
            "tz": "America/New_York", "tz_offset": -18000, "locale": "en-US",
        }
        mock_client.fetch_user_profile.return_value = {"title": "Engineer", "fields": {}}
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
        db.commit()
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
        db.commit()
        db.execute(
            "INSERT INTO sync_state (channel_id, last_synced_ts, last_synced_at, status) VALUES (?, ?, ?, ?)",
            (ch_id, "1700000002.000001", time.time(), "complete"),
        )
        db.commit()
        mock_client.fetch_messages_with_threads.return_value = [
            {"ts": "1700000003.000001", "user": "U1", "text": "new message"},
        ]
        sync_engine.sync_channel_messages("C1")
        # Verify oldest param was passed
        call_args = mock_client.fetch_messages_with_threads.call_args
        passed_oldest = call_args[1].get("oldest") if call_args[1] else call_args[0][1] if len(call_args[0]) > 1 else None
        assert passed_oldest == "1700000002.000001"

    def test_sync_extracts_reactions(self, sync_engine, mock_client, db):
        db.upsert_channel(slack_id="C1", name="general", type="channel")
        db.upsert_user(slack_id="U1", name="alice")
        db.upsert_user(slack_id="U2", name="bob")
        db.commit()
        mock_client.fetch_messages_with_threads.return_value = [
            {
                "ts": "1700000001.000001", "user": "U1", "text": "hello",
                "reactions": [{"name": "thumbsup", "users": ["U2"], "count": 1}],
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
        db.commit()
        mock_client.fetch_messages_with_threads.return_value = [
            {
                "ts": "1700000001.000001", "user": "U1", "text": "",
                "subtype": "huddle_thread",
                "room": {
                    "date_start": 1700000000, "date_end": 1700003600,
                    "has_ended": True, "participant_history": ["U1", "U2"],
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
        db.commit()
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
        db.commit()
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
        db.commit()
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
