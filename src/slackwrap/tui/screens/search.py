from __future__ import annotations
from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Static, ListView, Header, Footer
from textual.worker import get_current_worker
from slackwrap.tui.widgets.search_result import SearchResultItem


class SearchScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Who do you want to wrap?", id="search-title")
        yield Input(placeholder="Search for a person...", id="search-input")
        yield ListView(id="search-results")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if query:
            self._do_search(query)

    @work(exclusive=True, thread=True)
    def _do_search(self, query: str) -> None:
        worker = get_current_worker()
        app = self.app
        try:
            from slackwrap.slack_client import SlackClient
            client = SlackClient(token=app.token)
            users = client.search_users(query)
            dm_channels = client.fetch_dm_channels()
            dm_by_user = {ch["user"]: ch["id"] for ch in dm_channels}
            results = []
            for user in users:
                uid = user["id"]
                if uid in dm_by_user:
                    results.append({
                        "label": f"{user.get('real_name', user.get('name', uid))} (DM)",
                        "slack_id": uid, "type": "dm",
                        "user_name": user.get("real_name", user.get("name", uid)),
                    })
            if not worker.is_cancelled:
                self.call_from_thread(self._show_results, results)
        except Exception as e:
            if not worker.is_cancelled:
                self.call_from_thread(self.notify, f"Search failed: {e}", severity="error")

    def _show_results(self, results: list[dict]) -> None:
        list_view = self.query_one("#search-results", ListView)
        list_view.clear()
        for r in results:
            list_view.append(SearchResultItem(label=r["label"], slack_id=r["slack_id"],
                                               result_type=r["type"], user_name=r.get("user_name", "")))
        if not results:
            self.notify("No matches found")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, SearchResultItem):
            self.app.selected_user_slack_id = item.slack_id
            self.app.selected_user_name = item.user_name
            from slackwrap.tui.screens.sync import SyncScreen
            self.app.switch_screen(SyncScreen(target_user_slack_id=item.slack_id))
