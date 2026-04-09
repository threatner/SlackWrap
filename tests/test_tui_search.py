# tests/test_tui_search.py
from __future__ import annotations

def test_search_screen_creation():
    from slackwrap.tui.screens.search import SearchScreen
    screen = SearchScreen()
    assert screen is not None

def test_search_result_item_creation():
    from slackwrap.tui.widgets.search_result import SearchResultItem
    item = SearchResultItem(label="Alice Johnson (DM)", slack_id="U12345", result_type="dm", user_name="Alice Johnson")
    assert item.label_text == "Alice Johnson (DM)"
    assert item.slack_id == "U12345"
    assert item.result_type == "dm"
