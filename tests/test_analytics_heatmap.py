from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def heatmap_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    msgs = [
        (ch, u1, "1.0", "msg", 1700049600.0),   # Mon 14:00 UTC
        (ch, u2, "2.0", "msg", 1700053200.0),   # Mon 15:00 UTC
        (ch, u1, "3.0", "msg", 1700067600.0),   # Mon 19:00 UTC
        (ch, u2, "4.0", "msg", 1700136000.0),   # Tue 14:00 UTC
        (ch, u1, "5.0", "msg", 1700222400.0),   # Wed 14:00 UTC
        (ch, u2, "6.0", "msg", 1700222460.0),   # Wed 14:01 UTC
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts, text=text, created_at=created_at)
    db.commit()
    return db, u1, u2, ch

def test_heatmap_returns_data(heatmap_db):
    from slackwrap.analytics.heatmap import compute_heatmap
    db, u1, u2, ch = heatmap_db
    result = compute_heatmap(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert len(result.data) > 0
    assert len(result.x_labels) == 7
    assert len(result.y_labels) == 24

def test_heatmap_counts_match_total(heatmap_db):
    from slackwrap.analytics.heatmap import compute_heatmap
    db, u1, u2, ch = heatmap_db
    result = compute_heatmap(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    total = sum(count for hour_data in result.data.values() for count in hour_data.values())
    assert total == 6
