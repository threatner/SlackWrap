from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class StatCard(Widget):
    DEFAULT_CSS = """
    StatCard { height: 7; padding: 1 2; background: $panel; border: round $primary; }
    StatCard .stat-value { text-style: bold; text-align: center; width: 100%; }
    StatCard .stat-label { text-align: center; width: 100%; color: $text-muted; }
    StatCard .stat-sub { text-align: center; width: 100%; color: $text-disabled; }
    """

    def __init__(self, label: str, value: str, subtitle: str = "", **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.value_text = value
        self.subtitle_text = subtitle

    def compose(self) -> ComposeResult:
        yield Static(self.value_text, classes="stat-value")
        yield Static(self.label_text, classes="stat-label")
        if self.subtitle_text:
            yield Static(self.subtitle_text, classes="stat-sub")
