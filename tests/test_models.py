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
