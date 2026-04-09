from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def seeded_db(db):
    """DB with two users and a channel, 10 messages over 5 days."""
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="general", type="channel")
    db.commit()

    msgs = [
        (ch, u1, "1700042400.001", "hello world", 1700042400.0),       # Wed Nov 15 2023
        (ch, u1, "1700042700.001", "how are you", 1700042700.0),
        (ch, u2, "1700043000.001", "good thanks", 1700043000.0),
        (ch, u1, "1700128800.001", "morning", 1700128800.0),            # Thu Nov 16
        (ch, u2, "1700129100.001", "hey there", 1700129100.0),
        (ch, u1, "1700215200.001", "friday vibes", 1700215200.0),       # Fri Nov 17
        (ch, u2, "1700215500.001", "weekend soon", 1700215500.0),
        (ch, u1, "1700388000.001", "back to work", 1700388000.0),       # Sun Nov 19
        (ch, u2, "1700388300.001", "yep", 1700388300.0),
        (ch, u1, "1700474400.001", "new week", 1700474400.0),           # Mon Nov 20
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                          text=text, created_at=created_at)
    db.commit()
    return db, u1, u2, ch


def test_volume_total_messages(seeded_db):
    from slackwrap.analytics.volume import compute_volume
    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_messages == 10


def test_volume_per_user_split(seeded_db):
    from slackwrap.analytics.volume import compute_volume
    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.you_count == 6
    assert stats.them_count == 4
    assert stats.you_pct == 60.0
    assert stats.them_pct == 40.0


def test_volume_busiest_day(seeded_db):
    from slackwrap.analytics.volume import compute_volume
    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.busiest_day_count == 3  # Nov 15 has 3 messages


def test_volume_active_days(seeded_db):
    from slackwrap.analytics.volume import compute_volume
    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.active_days == 5


def test_volume_weekend_weekday_split(seeded_db):
    from slackwrap.analytics.volume import compute_volume
    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.weekend_count == 2  # Sun Nov 19 = 2 messages
    assert stats.weekday_count == 8


def test_volume_monthly_rank(seeded_db):
    from slackwrap.analytics.volume import compute_volume
    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert len(stats.monthly_rank) >= 1
    assert stats.monthly_rank[0][2] == 1
