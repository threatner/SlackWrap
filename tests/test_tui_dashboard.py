# tests/test_tui_dashboard.py
from __future__ import annotations

def test_dashboard_screen_creation():
    from slackwrap.tui.screens.dashboard import DashboardScreen
    screen = DashboardScreen()
    assert screen is not None

def test_format_duration():
    from slackwrap.tui.screens.dashboard import format_duration
    assert format_duration(3661) == "1h 01m"
    assert format_duration(45) == "45s"
    assert format_duration(120) == "2m"
    assert format_duration(90061) == "1d 1h 01m"
