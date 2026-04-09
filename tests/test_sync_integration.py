from __future__ import annotations
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
    client.fetch_dm_channels.return_value = [{"id": "D1", "user": "U_THEM"}]
    client.fetch_conversation_info.return_value = {
        "id": "D1", "is_im": True, "name": "", "created": 1680000000,
        "topic": {"value": ""}, "purpose": {"value": ""},
    }
    client.find_shared_channels.return_value = []
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
    client.fetch_pins.return_value = [
        {"type": "message", "message": {"ts": "1700000002.000001"},
         "created_by": "U_ME", "created": 1700000010},
    ]
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

    # Check messages (5 total)
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
