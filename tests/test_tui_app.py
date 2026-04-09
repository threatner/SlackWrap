# tests/test_tui_app.py
from __future__ import annotations
from unittest.mock import MagicMock


def test_app_creates_with_db_and_token():
    from slackwrap.tui.app import SlackWrapApp
    app = SlackWrapApp(db=MagicMock(), token="xoxp-test")
    assert app.db is not None
    assert app.token == "xoxp-test"


def test_app_has_title():
    from slackwrap.tui.app import SlackWrapApp
    app = SlackWrapApp(db=MagicMock(), token="xoxp-test")
    assert "SlackWrap" in app.TITLE


def test_app_has_keybindings():
    from slackwrap.tui.app import SlackWrapApp
    app = SlackWrapApp(db=MagicMock(), token="xoxp-test")
    binding_keys = [b.key for b in app.BINDINGS]
    assert "q" in binding_keys
