from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def conversation_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    msgs = [
        (ch, u1, "1700049600.001", "hey", 1700049600.0),          # Mon 14:00
        (ch, u2, "1700049720.001", "hi", 1700049720.0),           # +2min
        (ch, u1, "1700049900.001", "question", 1700049900.0),     # +3min
        (ch, u2, "1700050200.001", "answer", 1700050200.0),       # +5min
        (ch, u1, "1700050500.001", "thanks", 1700050500.0),       # +5min
        # Big gap (overnight) — should be excluded
        (ch, u2, "1700100000.001", "morning", 1700100000.0),      # ~14h gap
        (ch, u1, "1700100060.001", "hey", 1700100060.0),          # +1min
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                          text=text, created_at=created_at)
    db.commit()
    return db, u1, u2, ch

def test_response_time_excludes_long_gaps(conversation_db):
    from slackwrap.analytics.response_time import compute_response_times
    db, u1, u2, ch = conversation_db
    stats = compute_response_times(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_avg > 0
    assert stats.their_avg > 0

def test_response_time_your_vs_their(conversation_db):
    from slackwrap.analytics.response_time import compute_response_times
    db, u1, u2, ch = conversation_db
    stats = compute_response_times(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_median > 0
    assert stats.their_median > 0

def test_response_time_by_hour(conversation_db):
    from slackwrap.analytics.response_time import compute_response_times
    db, u1, u2, ch = conversation_db
    stats = compute_response_times(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert isinstance(stats.by_hour, dict)
