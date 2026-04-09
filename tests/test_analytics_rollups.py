from __future__ import annotations
import pytest

@pytest.fixture
def rollup_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    day = 86400
    base = 1700049600.0
    for i in range(20):
        ts = base + i * day
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"msg {i} hello world", created_at=ts)
    db.commit()
    return db, u1, u2

def test_compute_weekly_rollups(rollup_db):
    from slackwrap.analytics.rollups import compute_rollups
    db, u1, u2 = rollup_db
    compute_rollups(db, you_id=u1, them_id=u2, relationship_key=f"{u1}:{u2}")
    rows = db.execute("SELECT * FROM weekly_stats WHERE relationship_key = ?", (f"{u1}:{u2}",)).fetchall()
    assert len(rows) >= 1
    total = sum(r["message_count"] for r in rows)
    assert total == 20

def test_compute_monthly_rollups(rollup_db):
    from slackwrap.analytics.rollups import compute_rollups
    db, u1, u2 = rollup_db
    compute_rollups(db, you_id=u1, them_id=u2, relationship_key=f"{u1}:{u2}")
    rows = db.execute("SELECT * FROM monthly_stats WHERE relationship_key = ?", (f"{u1}:{u2}",)).fetchall()
    assert len(rows) >= 1
    total = sum(r["message_count"] for r in rows)
    assert total == 20

def test_rollups_are_idempotent(rollup_db):
    from slackwrap.analytics.rollups import compute_rollups
    db, u1, u2 = rollup_db
    key = f"{u1}:{u2}"
    compute_rollups(db, you_id=u1, them_id=u2, relationship_key=key)
    compute_rollups(db, you_id=u1, them_id=u2, relationship_key=key)
    rows = db.execute("SELECT * FROM weekly_stats WHERE relationship_key = ?", (key,)).fetchall()
    total = sum(r["message_count"] for r in rows)
    assert total == 20  # Not doubled
