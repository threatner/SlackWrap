# tests/test_analytics_streaks.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def streak_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    day = 86400
    base = 1700049600.0  # Mon Nov 15 2023 14:00 UTC
    timestamps = [base, base+day, base+2*day, base+3*day, base+4*day, base+8*day, base+9*day]
    for i, ts in enumerate(timestamps):
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001", text=f"msg {i}", created_at=ts)
    db.commit()
    return db, u1, u2, ch

def test_longest_streak(streak_db):
    from slackwrap.analytics.streaks import compute_streaks
    db, u1, u2, ch = streak_db
    stats = compute_streaks(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.longest_streak_days == 5

def test_current_streak(streak_db):
    from slackwrap.analytics.streaks import compute_streaks
    db, u1, u2, ch = streak_db
    stats = compute_streaks(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.current_streak_days == 2

def test_longest_gap(streak_db):
    from slackwrap.analytics.streaks import compute_streaks
    db, u1, u2, ch = streak_db
    stats = compute_streaks(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.longest_gap_seconds >= 259200  # 3 days

def test_milestones(streak_db):
    from slackwrap.analytics.streaks import compute_streaks
    db, u1, u2, ch = streak_db
    stats = compute_streaks(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert isinstance(stats.milestones, dict)
