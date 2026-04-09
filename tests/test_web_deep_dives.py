from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from slackwrap.web.app import create_app


@pytest.fixture
def dd_client(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(5):
        ts = 1700049600.0 + i * 86400
        db.upsert_message(channel_id=ch, user_id=u1 if i % 2 == 0 else u2,
                          slack_ts=f"{ts}.001", text=f"msg {i} hello :rocket:", created_at=ts)
    db.commit()
    app = create_app(db=db, you_id=u1, them_id=u2, your_name="Alice", their_name="Bob")
    return TestClient(app)


def test_deep_dives_index(dd_client):
    resp = dd_client.get("/deep-dives")
    assert resp.status_code == 200
    assert "Response Time" in resp.text


def test_deep_dives_response_time(dd_client):
    resp = dd_client.get("/deep-dives/response-time")
    assert resp.status_code == 200


def test_deep_dives_communication(dd_client):
    resp = dd_client.get("/deep-dives/communication")
    assert resp.status_code == 200


def test_deep_dives_activity(dd_client):
    resp = dd_client.get("/deep-dives/activity")
    assert resp.status_code == 200
