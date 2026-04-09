# tests/test_tui_sync.py
from __future__ import annotations

def test_sync_screen_creation():
    from slackwrap.tui.screens.sync import SyncScreen
    screen = SyncScreen(target_user_slack_id="U12345")
    assert screen.target_user_slack_id == "U12345"
