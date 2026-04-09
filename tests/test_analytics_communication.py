# tests/test_analytics_communication.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def comm_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    msgs = [
        (ch, u1, "1.0", "hello world how are you doing today", 1700049600.0),
        (ch, u1, "2.0", "I think we should review the code :rocket:", 1700049700.0),
        (ch, u2, "3.0", "yeah :thumbsup:", 1700049800.0),
        (ch, u2, "4.0", "looks good :thumbsup: :rocket:", 1700049900.0),
        (ch, u1, "5.0", "great", 1700050000.0),
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts, text=text, created_at=created_at)
    db.commit()
    msg3_id = db.execute("SELECT id FROM messages WHERE slack_ts = '3.0'").fetchone()["id"]
    db.execute("INSERT INTO reactions (message_id, user_id, emoji_name) VALUES (?, ?, ?)", (msg3_id, u1, "thumbsup"))
    db.execute("INSERT INTO reactions (message_id, user_id, emoji_name) VALUES (?, ?, ?)", (msg3_id, u1, "heart"))
    db.commit()
    return db, u1, u2, ch

def test_avg_word_count(comm_db):
    from slackwrap.analytics.communication import compute_communication
    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_avg_words > 0
    assert stats.their_avg_words > 0

def test_emoji_extraction(comm_db):
    from slackwrap.analytics.communication import compute_communication
    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_emoji_total >= 1
    assert stats.their_emoji_total >= 2

def test_reactions_given(comm_db):
    from slackwrap.analytics.communication import compute_communication
    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_reactions_given == 2

def test_emoji_diversity(comm_db):
    from slackwrap.analytics.communication import compute_communication
    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.emoji_diversity_you >= 1
    assert stats.emoji_diversity_them >= 1

def test_message_length_distribution(comm_db):
    from slackwrap.analytics.communication import compute_communication
    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert "short" in stats.message_length_distribution or "medium" in stats.message_length_distribution
