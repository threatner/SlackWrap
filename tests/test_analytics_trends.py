from __future__ import annotations
import time
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def trend_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    now = time.time()
    day = 86400
    for i in range(10):
        ts = now - (i * day)
        db.upsert_message(channel_id=ch, user_id=u1 if i % 2 == 0 else u2,
                          slack_ts=f"{ts}.001", text=f"recent {i}", created_at=ts)
    for i in range(5):
        ts = now - (40 + i) * day
        db.upsert_message(channel_id=ch, user_id=u1, slack_ts=f"{ts}.001",
                          text=f"older {i}", created_at=ts)
    db.commit()
    return db, u1, u2, ch

def test_30d_trend(trend_db):
    from slackwrap.analytics.trends import compute_trends
    db, u1, u2, ch = trend_db
    stats = compute_trends(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.last_30d_count == 10
    assert stats.prev_30d_count == 5
    assert stats.pct_change_30d == 100.0

def test_current_month(trend_db):
    from slackwrap.analytics.trends import compute_trends
    db, u1, u2, ch = trend_db
    stats = compute_trends(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.current_month != ""
    assert stats.current_month_count > 0
