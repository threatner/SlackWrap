from __future__ import annotations
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer
from slackwrap.db import Database


class SlackWrapApp(App):
    TITLE = "SlackWrap"
    SUB_TITLE = "Your Slack Year in Review"
    CSS_PATH = "styles/app.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("w", "open_web", "Web View"),
        Binding("c", "open_chat", "Chat"),
        Binding("s", "sync", "Sync"),
        Binding("slash", "switch_person", "Switch Person"),
    ]

    def __init__(self, db: Database, token: str, **kwargs):
        super().__init__(**kwargs)
        self.db = db
        self.token = token
        self.selected_user_slack_id: str | None = None
        self.selected_user_name: str = ""
        self.you_db_id: int | None = None
        self.them_db_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        from slackwrap.tui.screens.search import SearchScreen
        self.push_screen(SearchScreen())

    def action_quit(self) -> None:
        self.exit()

    def action_open_web(self) -> None:
        self.notify("Web view not yet available (Plan 4)")

    def action_open_chat(self) -> None:
        from slackwrap.tui.screens.chat import ChatScreen
        self.push_screen(ChatScreen())

    def action_sync(self) -> None:
        if self.selected_user_slack_id:
            from slackwrap.tui.screens.sync import SyncScreen
            self.push_screen(SyncScreen(target_user_slack_id=self.selected_user_slack_id))

    def action_switch_person(self) -> None:
        from slackwrap.tui.screens.search import SearchScreen
        self.push_screen(SearchScreen())
