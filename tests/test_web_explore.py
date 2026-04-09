from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from slackwrap.web.app import create_app


@pytest.fixture
def explore_client(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(5):
        ts = 1700049600.0 + i * 86400
        db.upsert_message(channel_id=ch, user_id=u1 if i % 2 == 0 else u2,
                          slack_ts=f"{ts}.001", text=f"msg {i}", created_at=ts)
    db.commit()
    app = create_app(db=db, you_id=u1, them_id=u2, your_name="Alice", their_name="Bob")
    return TestClient(app)


def test_explore_returns_html(explore_client):
    resp = explore_client.get("/explore")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_explore_has_chart_elements(explore_client):
    resp = explore_client.get("/explore")
    assert "canvas" in resp.text.lower() or "Chart" in resp.text
