# tests/test_tui_widgets.py
from __future__ import annotations


def test_stat_card_creation():
    from slackwrap.tui.widgets.stat_card import StatCard
    card = StatCard(label="Messages", value="4,821", subtitle="522 days")
    assert card.label_text == "Messages"
    assert card.value_text == "4,821"
    assert card.subtitle_text == "522 days"


def test_stat_card_defaults():
    from slackwrap.tui.widgets.stat_card import StatCard
    card = StatCard(label="Test", value="0")
    assert card.subtitle_text == ""
