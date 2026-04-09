from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from slackwrap.web.app import create_app


@pytest.fixture
def web_client():
    from slackwrap.db import Database
    db = Database(":memory:", check_same_thread=False)
    db.initialize()
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(10):
        ts = 1700049600.0 + i * 86400
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"msg {i} hello world :rocket:", created_at=ts)
    db.commit()
    app = create_app(db=db, you_id=u1, them_id=u2, your_name="Alice", their_name="Bob")
    yield TestClient(app)
    db.close()


def test_api_volume(web_client):
    resp = web_client.get("/api/volume")
    assert resp.status_code == 200
    assert resp.json()["total_messages"] == 10


def test_api_heatmap(web_client):
    resp = web_client.get("/api/heatmap")
    assert resp.status_code == 200
    assert "data" in resp.json()


def test_api_trends(web_client):
    resp = web_client.get("/api/trends")
    assert resp.status_code == 200
    assert "current_month" in resp.json()


def test_api_streaks(web_client):
    resp = web_client.get("/api/streaks")
    assert resp.status_code == 200
    assert "longest_streak_days" in resp.json()


def test_api_communication(web_client):
    resp = web_client.get("/api/communication")
    assert resp.status_code == 200
    assert "your_avg_words" in resp.json()


def test_api_response_times(web_client):
    resp = web_client.get("/api/response-times")
    assert resp.status_code == 200
    assert "your_median" in resp.json()


def test_api_relationship(web_client):
    resp = web_client.get("/api/relationship")
    assert resp.status_code == 200
    assert "reciprocity_index" in resp.json()
