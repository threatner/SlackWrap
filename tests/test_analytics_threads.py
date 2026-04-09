# tests/test_analytics_threads.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def thread_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    msgs = [
        (ch, u1, "1.0", "start", 1700049600.0, "1.0", 3),
        (ch, u2, "2.0", "another", 1700049700.0, "2.0", 0),
        (ch, u2, "1.1", "reply 1", 1700049610.0, "1.0", 0),
        (ch, u1, "1.2", "reply 2", 1700049620.0, "1.0", 0),
        (ch, u2, "1.3", "reply 3", 1700049630.0, "1.0", 0),
        (ch, u2, "3.0", "topic", 1700049800.0, "3.0", 2),
        (ch, u1, "3.1", "reply", 1700049810.0, "3.0", 0),
        (ch, u2, "3.2", "reply2", 1700049820.0, "3.0", 0),
    ]
    for channel_id, user_id, ts, text, created_at, thread_ts, reply_count in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts, text=text,
                          created_at=created_at, thread_ts=thread_ts, reply_count=reply_count)
    db.commit()
    return db, u1, u2, ch

def test_thread_breakdown(thread_db):
    from slackwrap.analytics.threads import compute_threads
    db, u1, u2, ch = thread_db
    stats = compute_threads(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_messages == 8
    assert stats.top_level == 3
    assert stats.in_threads == 5

def test_who_starts_threads(thread_db):
    from slackwrap.analytics.threads import compute_threads
    db, u1, u2, ch = thread_db
    stats = compute_threads(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.threads_started_by_you == 1
    assert stats.threads_started_by_them == 1

def test_thread_depth(thread_db):
    from slackwrap.analytics.threads import compute_threads
    db, u1, u2, ch = thread_db
    stats = compute_threads(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.deepest_thread == 3
