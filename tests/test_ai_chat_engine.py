# tests/test_ai_chat_engine.py
from __future__ import annotations
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def chat_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(20):
        ts = 1700049600.0 + i * 86400
        db.upsert_message(channel_id=ch, user_id=u1 if i % 2 == 0 else u2,
                          slack_ts=f"{ts}.001", text=f"msg {i} about projects", created_at=ts)
    db.commit()
    return db, u1, u2

def test_chat_engine_creation(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine
    db, u1, u2 = chat_db
    engine = ChatEngine(db=db, ollama=MagicMock(), you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    assert engine is not None

def test_chat_engine_responds(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine
    db, u1, u2 = chat_db
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.chat.return_value = "You have 20 messages."
    engine = ChatEngine(db=db, ollama=mock, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    assert len(engine.ask("How many messages?")) > 0

def test_chat_engine_maintains_history(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine
    db, u1, u2 = chat_db
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.chat.return_value = "Answer"
    engine = ChatEngine(db=db, ollama=mock, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    engine.ask("Q1")
    engine.ask("Q2")
    assert len(engine.history) == 4

def test_chat_engine_handles_unavailable(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine
    db, u1, u2 = chat_db
    mock = MagicMock()
    mock.is_available.return_value = False
    engine = ChatEngine(db=db, ollama=mock, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    resp = engine.ask("anything")
    assert "not available" in resp.lower() or "ollama" in resp.lower()

def test_chat_engine_executes_sql_in_response(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine
    db, u1, u2 = chat_db
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.chat.return_value = "Let me check.\n```sql\nSELECT COUNT(*) as cnt FROM messages\n```"
    engine = ChatEngine(db=db, ollama=mock, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    resp = engine.ask("How many messages?")
    assert "20" in resp  # SQL result should be appended
