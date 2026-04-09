from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def engine_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    msgs = [
        (ch, u1, "1.0", "hello world", 1700049600.0, "1.0", 0),
        (ch, u2, "2.0", "hey there :rocket:", 1700049700.0, "2.0", 0),
        (ch, u1, "3.0", "let's discuss", 1700049800.0, "3.0", 2),
        (ch, u2, "3.1", "sure", 1700049810.0, "3.0", 0),
        (ch, u1, "3.2", "ok great", 1700049820.0, "3.0", 0),
    ]
    for channel_id, user_id, ts, text, created_at, thread_ts, reply_count in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts, text=text,
                          created_at=created_at, thread_ts=thread_ts, reply_count=reply_count)
    db.commit()
    return db, u1, u2, ch

def test_engine_volume(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine
    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    stats = engine.volume(you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_messages == 5

def test_engine_threads(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine
    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    stats = engine.threads(you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_messages == 5
    assert stats.in_threads >= 2

def test_engine_communication(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine
    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    stats = engine.communication(you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_avg_words > 0

def test_engine_heatmap(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine
    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    result = engine.heatmap(you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert len(result.x_labels) == 7

def test_engine_text_search(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine
    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    results = engine.text_search("hello")
    assert len(results) >= 1

def test_engine_raw_sql(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine
    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    result = engine.raw_sql("SELECT COUNT(*) as cnt FROM messages")
    assert result.rows[0]["cnt"] == 5

def test_engine_rollups(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine
    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    engine.compute_rollups(you_id=u1, them_id=u2, relationship_key=f"{u1}:{u2}")
    rows = db.execute("SELECT * FROM weekly_stats").fetchall()
    assert len(rows) >= 1
