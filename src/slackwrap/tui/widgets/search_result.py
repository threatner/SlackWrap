from __future__ import annotations
from textual.widgets import ListItem, Label


class SearchResultItem(ListItem):
    def __init__(self, label: str, slack_id: str, result_type: str, user_name: str = "", **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.slack_id = slack_id
        self.result_type = result_type
        self.user_name = user_name

    def compose(self):
        yield Label(self.label_text)
