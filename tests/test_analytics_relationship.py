from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def rel_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    day = 86400
    base = 1700049600.0
    msgs = [
        (ch, u1, f"{base}.001", "morning", base),
        (ch, u2, f"{base + 100}.001", "hi", base + 100),
        (ch, u1, f"{base + day}.001", "morning", base + day),
        (ch, u2, f"{base + day + 50}.001", "yo", base + day + 50),
        (ch, u2, f"{base + 2*day}.001", "hey first", base + 2*day),
        (ch, u1, f"{base + 2*day + 200}.001", "sup", base + 2*day + 200),
        (ch, u1, f"{base + 3*day}.001", "gm", base + 3*day),
        (ch, u2, f"{base + 4*day}.001", "hello", base + 4*day),
        (ch, u1, f"{base + 4*day + 60}.001", "hey", base + 4*day + 60),
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts, text=text, created_at=created_at)
    db.commit()
    msg_id = db.execute("SELECT id FROM messages LIMIT 1").fetchone()["id"]
    db.execute("INSERT INTO pins (channel_id, user_id, message_ts, pinned_at) VALUES (?, ?, ?, ?)",
               (ch, u1, f"{base}.001", base + 500))
    db.commit()
    return db, u1, u2, ch

def test_conversation_initiations(rel_db):
    from slackwrap.analytics.relationship import compute_relationship
    db, u1, u2, ch = rel_db
    stats = compute_relationship(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.conversation_initiations_you == 3
    assert stats.conversation_initiations_them == 2

def test_reciprocity_index(rel_db):
    from slackwrap.analytics.relationship import compute_relationship
    db, u1, u2, ch = rel_db
    stats = compute_relationship(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert 0.0 < stats.reciprocity_index <= 1.0

def test_first_last_message(rel_db):
    from slackwrap.analytics.relationship import compute_relationship
    db, u1, u2, ch = rel_db
    stats = compute_relationship(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.first_message is not None
    assert stats.last_message is not None
    assert stats.first_message["text"] == "morning"

def test_pinned_highlights(rel_db):
    from slackwrap.analytics.relationship import compute_relationship
    db, u1, u2, ch = rel_db
    stats = compute_relationship(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert len(stats.pinned_highlights) == 1
