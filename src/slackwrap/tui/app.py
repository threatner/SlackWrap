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
        self._chat_engine = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        from slackwrap.tui.screens.search import SearchScreen
        self.push_screen(SearchScreen())

    def action_quit(self) -> None:
        self.exit()

    def action_open_web(self) -> None:
        if not self.you_db_id or not self.them_db_id:
            self.notify("No data loaded. Sync first.")
            return
        if not hasattr(self, '_web_server') or self._web_server is None:
            from slackwrap.web.server import WebServer
            self._web_server = WebServer(
                db=self.db, you_id=self.you_db_id, them_id=self.them_db_id,
                your_name="You", their_name=self.selected_user_name or "Them",
            )
            self._web_server.start()
        import webbrowser
        webbrowser.open(f"{self._web_server.url}/story")
        self.notify(f"Web view: {self._web_server.url}")

    def get_chat_engine(self):
        if self._chat_engine is None and self.you_db_id and self.them_db_id:
            from slackwrap.ai.ollama_client import OllamaClient
            from slackwrap.ai.chat_engine import ChatEngine
            ollama = OllamaClient()
            self._chat_engine = ChatEngine(
                db=self.db, ollama=ollama, you_id=self.you_db_id, them_id=self.them_db_id,
                your_name="You", their_name=self.selected_user_name or "Them",
            )
        return self._chat_engine

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
