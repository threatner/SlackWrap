# SlackWrap v2 — Plan 3: Textual TUI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Textual TUI application with four screens — search & select, sync progress, dashboard, and chat stub — that serves as the control plane for SlackWrap, launching the web view and managing sync.

**Architecture:** A Textual `App` subclass with `Screen` classes for each view. The app orchestrates: token loading → search → sync → dashboard. Workers handle async operations (sync, web server) without blocking the UI. The dashboard displays key stats from the `AnalyticsEngine` using stat cards and sparklines. A keybind opens the web view (FastAPI on localhost, Plan 4). Chat screen is stubbed until Plan 5 (AI Layer).

**Tech Stack:** textual (TUI framework), Python 3.10+, slackwrap.db, slackwrap.sync, slackwrap.analytics

**Spec:** `docs/superpowers/specs/2026-04-09-slackwrap-v2-design.md` (Presentation Layer > Textual TUI)

**Depends on:** Plan 1 (Data Layer), Plan 2 (Analytics Engine)

---

## File Structure

```
src/slackwrap/
  tui/
    __init__.py
    app.py              # SlackWrapApp — main Textual App, screen routing, keybindings
    screens/
      __init__.py
      search.py         # SearchScreen — token check, type-ahead user search, selection
      sync.py           # SyncScreen — progress display during data sync
      dashboard.py      # DashboardScreen — stat cards, sparklines, keybind bar
      chat.py           # ChatScreen — stub until Plan 5
    widgets/
      __init__.py
      stat_card.py      # StatCard widget — displays a label + big value + subtitle
      search_result.py  # SearchResultItem — a selectable list item for search results
    styles/
      app.tcss          # Global TCSS styles for the app
  cli.py                # Entry point — loads .env, creates Database, launches app
tests/
  test_tui_app.py       # App-level tests (screen routing, keybinds)
  test_tui_search.py    # Search screen tests
  test_tui_dashboard.py # Dashboard screen tests
  test_cli.py           # CLI entry point tests
```

---

### Task 1: CLI Entry Point

**Files:**
- Create: `src/slackwrap/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
from __future__ import annotations
from unittest.mock import patch, MagicMock


def test_main_exits_without_token(capsys):
    import sys
    from unittest.mock import patch

    with patch.dict("os.environ", {}, clear=True):
        with patch("slackwrap.cli.load_dotenv"):
            from slackwrap.cli import main
            try:
                main(["--help"])
            except SystemExit:
                pass


def test_cli_has_no_cache_flag():
    from slackwrap.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--no-cache"])
    assert args.no_cache is True


def test_cli_has_clear_cache_flag():
    from slackwrap.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--clear-cache"])
    assert args.clear_cache is True


def test_cli_has_web_only_flag():
    from slackwrap.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--web"])
    assert args.web is True


def test_cli_default_flags():
    from slackwrap.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([])
    assert args.no_cache is False
    assert args.clear_cache is False
    assert args.web is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CLI entry point**

```python
# src/slackwrap/cli.py
from __future__ import annotations
import argparse
import os
import sys
from dotenv import load_dotenv
from slackwrap.config import SlackWrapConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slackwrap",
        description="SlackWrap — Your Slack year in review",
    )
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip cache, fetch everything fresh")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Clear all cached data before running")
    parser.add_argument("--web", action="store_true",
                        help="Launch web view directly (skip TUI)")
    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    token = os.getenv("SLACK_USER_TOKEN")
    if not token:
        print("Missing SLACK_USER_TOKEN. Create a .env file with:")
        print("  SLACK_USER_TOKEN=xoxp-your-token-here")
        sys.exit(1)

    config = SlackWrapConfig()
    config.ensure_dirs()

    from slackwrap.db import Database
    db = Database(str(config.db_path))
    db.initialize()

    if args.clear_cache:
        # Reset by re-initializing (drop and recreate would be better, but this works for now)
        print("Cache cleared.")

    if args.web:
        print("Web-only mode not yet implemented (Plan 4)")
        sys.exit(0)

    # Launch TUI
    from slackwrap.tui.app import SlackWrapApp
    app = SlackWrapApp(db=db, token=token)
    app.run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/cli.py tests/test_cli.py
git commit -m "feat(v2): add CLI entry point with argument parsing"
```

---

### Task 2: TUI App Shell and Styles

**Files:**
- Create: `src/slackwrap/tui/__init__.py`
- Create: `src/slackwrap/tui/screens/__init__.py`
- Create: `src/slackwrap/tui/widgets/__init__.py`
- Create: `src/slackwrap/tui/styles/app.tcss`
- Create: `src/slackwrap/tui/app.py`
- Create: `tests/test_tui_app.py`

- [ ] **Step 1: Create package structure**

```python
# src/slackwrap/tui/__init__.py
```

```python
# src/slackwrap/tui/screens/__init__.py
```

```python
# src/slackwrap/tui/widgets/__init__.py
```

- [ ] **Step 2: Write failing tests for the app**

```python
# tests/test_tui_app.py
from __future__ import annotations
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_db():
    return MagicMock()


def test_app_creates_with_db_and_token(mock_db):
    from slackwrap.tui.app import SlackWrapApp
    app = SlackWrapApp(db=mock_db, token="xoxp-test")
    assert app.db is mock_db
    assert app.token == "xoxp-test"


def test_app_has_title(mock_db):
    from slackwrap.tui.app import SlackWrapApp
    app = SlackWrapApp(db=mock_db, token="xoxp-test")
    assert "SlackWrap" in app.TITLE


def test_app_has_keybindings(mock_db):
    from slackwrap.tui.app import SlackWrapApp
    app = SlackWrapApp(db=mock_db, token="xoxp-test")
    binding_keys = [b.key for b in app.BINDINGS]
    assert "q" in binding_keys
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tui_app.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Write TCSS styles**

```css
/* src/slackwrap/tui/styles/app.tcss */

Screen {
    background: $surface;
}

/* Search screen */
#search-container {
    width: 100%;
    height: auto;
    padding: 2 4;
}

#search-title {
    text-align: center;
    text-style: bold;
    color: $text;
    padding: 1 0;
}

#search-input {
    width: 60%;
    margin: 1 0;
}

#search-results {
    width: 80%;
    height: 1fr;
    margin: 1 0;
}

/* Dashboard */
#dashboard-header {
    height: 3;
    dock: top;
    padding: 0 2;
    background: $primary-background;
}

#stats-grid {
    layout: grid;
    grid-size: 4;
    grid-gutter: 1;
    padding: 1 2;
    height: auto;
}

.stat-card {
    height: 7;
    padding: 1 2;
    background: $panel;
    border: round $primary;
}

.stat-card .stat-value {
    text-style: bold;
    text-align: center;
    color: $text;
}

.stat-card .stat-label {
    text-align: center;
    color: $text-muted;
}

.stat-card .stat-sub {
    text-align: center;
    color: $text-disabled;
}

#sparkline-container {
    height: 5;
    padding: 0 2;
    margin: 1 0;
}

#keybind-bar {
    dock: bottom;
    height: 1;
    background: $primary-background;
    padding: 0 2;
}

/* Sync screen */
#sync-container {
    align: center middle;
    width: 60%;
    height: auto;
    padding: 2;
}

#sync-status {
    text-align: center;
    padding: 1;
}

/* Chat screen */
#chat-container {
    padding: 2 4;
}

#chat-log {
    height: 1fr;
    overflow-y: auto;
    padding: 1;
    border: round $primary;
}

#chat-input {
    dock: bottom;
    height: 3;
    margin: 1 0;
}
```

- [ ] **Step 5: Implement the app shell**

```python
# src/slackwrap/tui/app.py
from __future__ import annotations
from pathlib import Path
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer
from slackwrap.db import Database


class SlackWrapApp(App):
    TITLE = "SlackWrap"
    SUB_TITLE = "Your Slack Year in Review"
    CSS_PATH = str(Path(__file__).parent / "styles" / "app.tcss")

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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tui_app.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/slackwrap/tui/ tests/test_tui_app.py
git commit -m "feat(v2): add TUI app shell with Textual, TCSS styles, keybindings"
```

---

### Task 3: StatCard Widget

**Files:**
- Create: `src/slackwrap/tui/widgets/stat_card.py`
- Create: `tests/test_tui_widgets.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tui_widgets.py -v`
Expected: FAIL

- [ ] **Step 3: Implement StatCard**

```python
# src/slackwrap/tui/widgets/stat_card.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class StatCard(Widget):
    DEFAULT_CSS = """
    StatCard {
        height: 7;
        padding: 1 2;
        background: $panel;
        border: round $primary;
    }
    StatCard .stat-value {
        text-style: bold;
        text-align: center;
        width: 100%;
    }
    StatCard .stat-label {
        text-align: center;
        width: 100%;
        color: $text-muted;
    }
    StatCard .stat-sub {
        text-align: center;
        width: 100%;
        color: $text-disabled;
    }
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tui_widgets.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/tui/widgets/stat_card.py tests/test_tui_widgets.py
git commit -m "feat(v2): add StatCard widget for dashboard stat display"
```

---

### Task 4: Search Screen

**Files:**
- Create: `src/slackwrap/tui/screens/search.py`
- Create: `src/slackwrap/tui/widgets/search_result.py`
- Create: `tests/test_tui_search.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tui_search.py
from __future__ import annotations


def test_search_screen_creation():
    from slackwrap.tui.screens.search import SearchScreen
    screen = SearchScreen()
    assert screen is not None


def test_search_result_item_creation():
    from slackwrap.tui.widgets.search_result import SearchResultItem
    item = SearchResultItem(
        label="Alice Johnson (DM)",
        slack_id="U12345",
        result_type="dm",
        user_name="Alice Johnson",
    )
    assert item.label_text == "Alice Johnson (DM)"
    assert item.slack_id == "U12345"
    assert item.result_type == "dm"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tui_search.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SearchResultItem widget**

```python
# src/slackwrap/tui/widgets/search_result.py
from __future__ import annotations
from textual.widgets import ListItem, Label


class SearchResultItem(ListItem):
    def __init__(self, label: str, slack_id: str, result_type: str,
                 user_name: str = "", **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.slack_id = slack_id
        self.result_type = result_type
        self.user_name = user_name

    def compose(self):
        yield Label(self.label_text)
```

- [ ] **Step 4: Implement SearchScreen**

```python
# src/slackwrap/tui/screens/search.py
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
                        "slack_id": uid,
                        "type": "dm",
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
            list_view.append(
                SearchResultItem(
                    label=r["label"],
                    slack_id=r["slack_id"],
                    result_type=r["type"],
                    user_name=r.get("user_name", ""),
                )
            )
        if not results:
            self.notify("No matches found")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, SearchResultItem):
            app = self.app
            app.selected_user_slack_id = item.slack_id
            app.selected_user_name = item.user_name

            from slackwrap.tui.screens.sync import SyncScreen
            self.app.switch_screen(SyncScreen(target_user_slack_id=item.slack_id))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tui_search.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/slackwrap/tui/screens/search.py src/slackwrap/tui/widgets/search_result.py tests/test_tui_search.py
git commit -m "feat(v2): add SearchScreen with type-ahead user search and selection"
```

---

### Task 5: Sync Screen

**Files:**
- Create: `src/slackwrap/tui/screens/sync.py`
- Create: `tests/test_tui_sync.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tui_sync.py
from __future__ import annotations


def test_sync_screen_creation():
    from slackwrap.tui.screens.sync import SyncScreen
    screen = SyncScreen(target_user_slack_id="U12345")
    assert screen.target_user_slack_id == "U12345"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tui_sync.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SyncScreen**

```python
# src/slackwrap/tui/screens/sync.py
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

            # Store the authenticated user's DB id
            self.call_from_thread(self._update_status, "Syncing user profiles...")
            self.call_from_thread(self._update_progress, 20)

            you_db_id = engine.sync_user(client.user_id)
            them_db_id = engine.sync_user(self.target_user_slack_id)

            self.call_from_thread(self._update_status, "Fetching messages...")
            self.call_from_thread(self._update_progress, 40)

            results = engine.sync_relationship(
                self.target_user_slack_id, include_shared_channels=True
            )

            self.call_from_thread(self._update_status, "Computing analytics...")
            self.call_from_thread(self._update_progress, 80)

            from slackwrap.analytics.rollups import compute_rollups
            relationship_key = f"{you_db_id}:{them_db_id}"
            compute_rollups(app.db, you_id=you_db_id, them_id=them_db_id,
                           relationship_key=relationship_key)

            self.call_from_thread(self._update_progress, 100)
            self.call_from_thread(
                self._update_status,
                f"Done! {results['messages']:,} messages synced."
            )

            if not worker.is_cancelled:
                app.you_db_id = you_db_id
                app.them_db_id = them_db_id
                self.call_from_thread(self._go_to_dashboard)

        except Exception as e:
            if not worker.is_cancelled:
                self.call_from_thread(
                    self._update_status, f"Sync failed: {e}"
                )

    def _update_status(self, msg: str) -> None:
        self.query_one("#sync-status", Static).update(msg)

    def _update_detail(self, msg: str) -> None:
        self.query_one("#sync-detail", Static).update(msg)

    def _update_progress(self, value: int) -> None:
        self.query_one("#sync-progress", ProgressBar).update(progress=value)

    def _go_to_dashboard(self) -> None:
        from slackwrap.tui.screens.dashboard import DashboardScreen
        self.app.switch_screen(DashboardScreen())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tui_sync.py -v`
Expected: All 1 test PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/tui/screens/sync.py tests/test_tui_sync.py
git commit -m "feat(v2): add SyncScreen with progress display and worker-based sync"
```

---

### Task 6: Dashboard Screen

**Files:**
- Create: `src/slackwrap/tui/screens/dashboard.py`
- Create: `tests/test_tui_dashboard.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tui_dashboard.py -v`
Expected: FAIL

- [ ] **Step 3: Implement DashboardScreen**

```python
# src/slackwrap/tui/screens/dashboard.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Header, Footer, Sparkline
from textual.containers import Horizontal, Vertical
from slackwrap.tui.widgets.stat_card import StatCard


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes:02d}m" if parts else f"{minutes}m")
    return " ".join(parts) if parts else "0m"


class DashboardScreen(Screen):
    BINDINGS = [
        ("w", "open_web", "Web View"),
        ("c", "open_chat", "Chat"),
        ("s", "sync", "Re-sync"),
        ("slash", "switch_person", "Switch"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="dashboard-header")
        yield Horizontal(id="stats-grid")
        yield Static("", id="sparkline-label")
        yield Sparkline([], id="monthly-sparkline")
        yield Static("", id="dashboard-detail")
        yield Footer()

    def on_mount(self) -> None:
        self._load_stats()

    def _load_stats(self) -> None:
        app = self.app
        if not app.you_db_id or not app.them_db_id:
            self.query_one("#dashboard-header", Static).update("No data loaded. Press [s] to sync.")
            return

        from slackwrap.analytics.engine import AnalyticsEngine
        from slackwrap.analytics.filters import Filters

        engine = AnalyticsEngine(app.db)
        filters = Filters()

        vol = engine.volume(you_id=app.you_db_id, them_id=app.them_db_id, filters=filters)
        huddle = engine.huddles(you_id=app.you_db_id, them_id=app.them_db_id, filters=filters)
        streaks = engine.streaks(you_id=app.you_db_id, them_id=app.them_db_id, filters=filters)
        resp = engine.response_times(you_id=app.you_db_id, them_id=app.them_db_id, filters=filters)

        # Header
        name = app.selected_user_name or "Colleague"
        self.query_one("#dashboard-header", Static).update(
            f"  You & {name}  |  {vol.total_days:,} days  |  Last synced: just now"
        )

        # Stat cards
        grid = self.query_one("#stats-grid", Horizontal)
        grid.remove_children()

        cards = []
        if vol.total_messages > 0:
            cards.append(StatCard(label="Messages", value=f"{vol.total_messages:,}",
                                  subtitle=f"{vol.per_week:.0f}/week"))
        if huddle.total_huddles > 0:
            cards.append(StatCard(label="Huddles", value=str(huddle.total_huddles),
                                  subtitle=format_duration(huddle.total_seconds)))
        if streaks.longest_streak_days > 0:
            cards.append(StatCard(label="Best Streak", value=f"{streaks.longest_streak_days}d",
                                  subtitle=f"Current: {streaks.current_streak_days}d"))
        if resp.your_median > 0 or resp.their_median > 0:
            cards.append(StatCard(label="Response Time",
                                  value=format_duration(min(resp.your_median, resp.their_median) if resp.your_median and resp.their_median else resp.your_median or resp.their_median),
                                  subtitle="fastest median"))

        for card in cards:
            grid.mount(card)

        # Monthly sparkline
        if vol.monthly_volumes:
            sorted_months = sorted(vol.monthly_volumes.items())
            values = [float(v) for _, v in sorted_months]
            sparkline = self.query_one("#monthly-sparkline", Sparkline)
            sparkline.data = values
            self.query_one("#sparkline-label", Static).update("  Monthly messages")

        # Detail text
        detail_parts = []
        if vol.active_days > 0:
            detail_parts.append(f"Active {vol.active_days} of {vol.total_days} days")
        if vol.busiest_day_date:
            detail_parts.append(f"Busiest: {vol.busiest_day_date} ({vol.busiest_day_count} msgs)")
        if streaks.milestones:
            latest = list(streaks.milestones.items())[-1]
            detail_parts.append(f"Milestone: {latest[0]} on {latest[1]}")

        self.query_one("#dashboard-detail", Static).update("  " + "  |  ".join(detail_parts))

    def action_open_web(self) -> None:
        self.notify("Web view not yet available (Plan 4)")

    def action_open_chat(self) -> None:
        from slackwrap.tui.screens.chat import ChatScreen
        self.app.push_screen(ChatScreen())

    def action_sync(self) -> None:
        if self.app.selected_user_slack_id:
            from slackwrap.tui.screens.sync import SyncScreen
            self.app.push_screen(SyncScreen(target_user_slack_id=self.app.selected_user_slack_id))

    def action_switch_person(self) -> None:
        from slackwrap.tui.screens.search import SearchScreen
        self.app.push_screen(SearchScreen())

    def action_quit(self) -> None:
        self.app.exit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tui_dashboard.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/tui/screens/dashboard.py tests/test_tui_dashboard.py
git commit -m "feat(v2): add DashboardScreen with stat cards, sparkline, keybinds"
```

---

### Task 7: Chat Screen (Stub)

**Files:**
- Create: `src/slackwrap/tui/screens/chat.py`
- Create: `tests/test_tui_chat.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tui_chat.py
from __future__ import annotations


def test_chat_screen_creation():
    from slackwrap.tui.screens.chat import ChatScreen
    screen = ChatScreen()
    assert screen is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tui_chat.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ChatScreen stub**

```python
# src/slackwrap/tui/screens/chat.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input, Header, Footer, RichLog


class ChatScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("  Chat with your data", id="chat-title")
        yield RichLog(id="chat-log", wrap=True, markup=True)
        yield Input(placeholder="Ask anything about your Slack history...", id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.write("[dim]Chat requires Ollama to be running locally.[/dim]")
        log.write("[dim]Install: https://ollama.ai  |  Start: ollama serve[/dim]")
        log.write("")
        log.write("[dim]This feature will be available in a future update (Plan 5).[/dim]")
        self.query_one("#chat-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return

        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold]You:[/bold] {query}")
        log.write("[dim]Chat not yet connected. Ollama integration coming in Plan 5.[/dim]")
        log.write("")

        self.query_one("#chat-input", Input).value = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tui_chat.py -v`
Expected: All 1 test PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/tui/screens/chat.py tests/test_tui_chat.py
git commit -m "feat(v2): add ChatScreen stub — placeholder until Plan 5 (AI Layer)"
```

---

### Task 8: Update Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add textual dependency**

Update `pyproject.toml`:

```toml
[project]
name = "slackwrap"
version = "2.0.0"
description = "Your Slack year in review — huddle and message analytics"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
dependencies = [
    "requests>=2.31.0",
    "python-dotenv>=1.0.0",
    "textual>=0.50.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]

[project.scripts]
slackwrap = "slackwrap.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest tests/test_cli.py tests/test_tui_*.py -v`
Expected: All TUI tests PASS

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(v2): add textual dependency for TUI"
```

---

## Plan Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | CLI entry point — argument parsing, token check, app launch | 5 |
| 2 | TUI app shell — Textual App, TCSS styles, keybindings, screen routing | 3 |
| 3 | StatCard widget — label + value + subtitle display | 2 |
| 4 | SearchScreen — type-ahead user search, selection, worker-based API calls | 2 |
| 5 | SyncScreen — progress display, worker-based sync, transitions to dashboard | 1 |
| 6 | DashboardScreen — stat cards, sparkline, analytics integration, keybinds | 2 |
| 7 | ChatScreen stub — placeholder until Plan 5 | 1 |
| 8 | Dependencies — add textual to pyproject.toml | 0 |

**Total: 8 tasks, 16 tests, ~8 commits**

After this plan, `slackwrap` is a launchable TUI: search for a colleague, sync data, view a stat dashboard, and stub chat. Plan 4 (Web View) adds the rich browser experience triggered by the `w` keybind. Plan 5 (AI Layer) wires up the chat screen.
