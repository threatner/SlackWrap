# tests/test_tui_chat.py
from __future__ import annotations

def test_chat_screen_creation():
    from slackwrap.tui.screens.chat import ChatScreen
    screen = ChatScreen()
    assert screen is not None
