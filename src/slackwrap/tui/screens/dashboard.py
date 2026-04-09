from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Header, Footer, Sparkline
from textual.containers import Horizontal
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
        ("w", "open_web", "Web View"), ("c", "open_chat", "Chat"),
        ("s", "sync", "Re-sync"), ("slash", "switch_person", "Switch"), ("q", "quit", "Quit"),
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

        name = app.selected_user_name or "Colleague"
        self.query_one("#dashboard-header", Static).update(
            f"  You & {name}  |  {vol.total_days:,} days  |  Last synced: just now"
        )
        grid = self.query_one("#stats-grid", Horizontal)
        grid.remove_children()
        cards = []
        if vol.total_messages > 0:
            cards.append(StatCard(label="Messages", value=f"{vol.total_messages:,}", subtitle=f"{vol.per_week:.0f}/week"))
        if huddle.total_huddles > 0:
            cards.append(StatCard(label="Huddles", value=str(huddle.total_huddles), subtitle=format_duration(huddle.total_seconds)))
        if streaks.longest_streak_days > 0:
            cards.append(StatCard(label="Best Streak", value=f"{streaks.longest_streak_days}d", subtitle=f"Current: {streaks.current_streak_days}d"))
        if resp.your_median > 0 or resp.their_median > 0:
            fastest = min(v for v in [resp.your_median, resp.their_median] if v > 0)
            cards.append(StatCard(label="Response Time", value=format_duration(fastest), subtitle="fastest median"))
        for card in cards:
            grid.mount(card)
        if vol.monthly_volumes:
            sorted_months = sorted(vol.monthly_volumes.items())
            values = [float(v) for _, v in sorted_months]
            self.query_one("#monthly-sparkline", Sparkline).data = values
            self.query_one("#sparkline-label", Static).update("  Monthly messages")
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
        self.app.action_open_web()

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
