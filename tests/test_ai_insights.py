# tests/test_ai_insights.py
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def insights_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(30):
        ts = 1700049600.0 + i * 86400
        db.upsert_message(channel_id=ch, user_id=u1 if i % 2 == 0 else u2,
                          slack_ts=f"{ts}.001", text=f"msg {i} about work", created_at=ts)
    db.commit()
    return db, u1, u2, ch

def test_generate_insights_stores_in_db(insights_db):
    from slackwrap.ai.insights import generate_insights
    db, u1, u2, ch = insights_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.chat_model = "test-model"
    mock_ollama.chat_json.return_value = {"facts": ["f1", "f2", "f3", "f4", "f5"]}
    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=f"{u1}:{u2}", your_name="Alice", their_name="Bob")
    rows = db.execute("SELECT * FROM ai_insights WHERE relationship_key = ?", (f"{u1}:{u2}",)).fetchall()
    assert len(rows) >= 1

def test_generate_insights_skips_when_cached(insights_db):
    from slackwrap.ai.insights import generate_insights
    db, u1, u2, ch = insights_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.chat_model = "test-model"
    mock_ollama.chat_json.return_value = {"facts": ["a", "b", "c", "d", "e"]}
    key = f"{u1}:{u2}"
    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=key, your_name="Alice", their_name="Bob")
    c1 = mock_ollama.chat_json.call_count
    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=key, your_name="Alice", their_name="Bob")
    assert mock_ollama.chat_json.call_count == c1

def test_generate_insights_skips_when_unavailable(insights_db):
    from slackwrap.ai.insights import generate_insights
    db, u1, u2, ch = insights_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = False
    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=f"{u1}:{u2}", your_name="Alice", their_name="Bob")
    assert db.execute("SELECT COUNT(*) as c FROM ai_insights").fetchone()["c"] == 0

def test_get_cached_insights(insights_db):
    from slackwrap.ai.insights import generate_insights, get_cached_insights
    db, u1, u2, ch = insights_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.chat_model = "test-model"
    mock_ollama.chat_json.return_value = {"facts": ["f1", "f2", "f3", "f4", "f5"]}
    key = f"{u1}:{u2}"
    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=key, your_name="Alice", their_name="Bob")
    cached = get_cached_insights(db, relationship_key=key)
    assert len(cached) >= 1
    assert any(c["insight_type"] == "fun_facts" for c in cached)
