from __future__ import annotations
import pytest


@pytest.fixture
def sampler_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(60):
        ts = 1700049600.0 + i * 86400
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"message {i} about work and fun", created_at=ts)
    db.commit()
    return db, u1, u2, ch


def test_sample_messages_returns_limited_set(sampler_db):
    from slackwrap.ai.sampler import sample_messages
    db, u1, u2, ch = sampler_db
    samples = sample_messages(db, user_id=u1, channel_id=ch, per_month=5)
    assert len(samples) <= 20


def test_sample_messages_includes_text(sampler_db):
    from slackwrap.ai.sampler import sample_messages
    db, u1, u2, ch = sampler_db
    samples = sample_messages(db, user_id=u1, channel_id=ch, per_month=5)
    assert all("text" in s for s in samples)


def test_sample_messages_for_specific_user(sampler_db):
    from slackwrap.ai.sampler import sample_messages
    db, u1, u2, ch = sampler_db
    samples = sample_messages(db, user_id=u1, channel_id=ch, per_month=5)
    assert all(s["user_id"] == u1 for s in samples)


def test_sample_conversation_windows(sampler_db):
    from slackwrap.ai.sampler import sample_conversation_windows
    db, u1, u2, ch = sampler_db
    windows = sample_conversation_windows(db, channel_id=ch, window_size=10, stride=5)
    assert len(windows) > 0
    assert all(len(w["messages"]) <= 10 for w in windows)


def test_build_stats_summary(sampler_db):
    from slackwrap.ai.sampler import build_stats_summary
    from slackwrap.analytics.engine import AnalyticsEngine
    db, u1, u2, ch = sampler_db
    engine = AnalyticsEngine(db)
    summary = build_stats_summary(engine, you_id=u1, them_id=u2)
    assert "total_messages" in summary
