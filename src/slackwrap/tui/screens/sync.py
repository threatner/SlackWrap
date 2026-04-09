from __future__ import annotations
from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, ProgressBar, Header, Footer
from textual.worker import get_current_worker


class SyncScreen(Screen):
    def __init__(self, target_user_slack_id: str, **kwargs):
        super().__init__(**kwargs)
        self.target_user_slack_id = target_user_slack_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Syncing data...", id="sync-status")
        yield ProgressBar(total=100, id="sync-progress")
        yield Static("", id="sync-detail")
        yield Footer()

    def on_mount(self) -> None:
        self._run_sync()

    @work(exclusive=True, thread=True)
    def _run_sync(self) -> None:
        worker = get_current_worker()
        app = self.app
        try:
            self.call_from_thread(self._update_status, "Connecting to Slack...")
            self.call_from_thread(self._update_progress, 10)
            from slackwrap.slack_client import SlackClient
            from slackwrap.sync import SyncEngine
            client = SlackClient(token=app.token)
            engine = SyncEngine(db=app.db, client=client)
            self.call_from_thread(self._update_status, "Syncing user profiles...")
            self.call_from_thread(self._update_progress, 20)
            you_db_id = engine.sync_user(client.user_id)
            them_db_id = engine.sync_user(self.target_user_slack_id)
            self.call_from_thread(self._update_status, "Fetching messages...")
            self.call_from_thread(self._update_progress, 40)
            results = engine.sync_relationship(self.target_user_slack_id, include_shared_channels=True)
            self.call_from_thread(self._update_status, "Computing analytics...")
            self.call_from_thread(self._update_progress, 80)
            from slackwrap.analytics.rollups import compute_rollups
            relationship_key = f"{you_db_id}:{them_db_id}"
            compute_rollups(app.db, you_id=you_db_id, them_id=them_db_id, relationship_key=relationship_key)
            self.call_from_thread(self._update_progress, 100)
            self.call_from_thread(self._update_status, f"Done! {results['messages']:,} messages synced.")
            if not worker.is_cancelled:
                app.you_db_id = you_db_id
                app.them_db_id = them_db_id
                self.call_from_thread(self._go_to_dashboard)
        except Exception as e:
            if not worker.is_cancelled:
                self.call_from_thread(self._update_status, f"Sync failed: {e}")

    def _update_status(self, msg: str) -> None:
        self.query_one("#sync-status", Static).update(msg)

    def _update_progress(self, value: int) -> None:
        self.query_one("#sync-progress", ProgressBar).update(progress=value)

    def _go_to_dashboard(self) -> None:
        from slackwrap.tui.screens.dashboard import DashboardScreen
        self.app.switch_screen(DashboardScreen())
