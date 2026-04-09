from __future__ import annotations
import time
import requests


def test_web_server_starts_and_stops():
    from slackwrap.web.server import WebServer
    from slackwrap.db import Database
    db = Database(":memory:")
    db.initialize()
    server = WebServer(db=db, you_id=1, them_id=2, your_name="You", their_name="Them")
    server.start()
    time.sleep(0.5)
    try:
        resp = requests.get(f"http://127.0.0.1:{server.port}/health", timeout=2)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        server.stop()
        db.close()


def test_web_server_picks_available_port():
    from slackwrap.web.server import WebServer
    from slackwrap.db import Database
    db = Database(":memory:")
    db.initialize()
    server = WebServer(db=db, you_id=1, them_id=2)
    assert server.port > 0
    db.close()


def test_web_server_returns_url():
    from slackwrap.web.server import WebServer
    from slackwrap.db import Database
    db = Database(":memory:")
    db.initialize()
    server = WebServer(db=db, you_id=1, them_id=2)
    assert f"http://127.0.0.1:{server.port}" in server.url
    db.close()
