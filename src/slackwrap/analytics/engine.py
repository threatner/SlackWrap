from __future__ import annotations

from slackwrap.analytics.filters import Filters
from slackwrap.analytics.types import (
    VolumeStats,
    HuddleStats,
    ResponseTimeStats,
    ThreadStats,
    CommunicationStats,
    StreakStats,
    TrendStats,
    HeatmapResult,
    RelationshipStats,
    QueryResult,
)
from slackwrap.analytics.volume import compute_volume
from slackwrap.analytics.huddles import compute_huddles
from slackwrap.analytics.response_time import compute_response_times
from slackwrap.analytics.threads import compute_threads
from slackwrap.analytics.communication import compute_communication
from slackwrap.analytics.streaks import compute_streaks
from slackwrap.analytics.trends import compute_trends
from slackwrap.analytics.heatmap import compute_heatmap
from slackwrap.analytics.relationship import compute_relationship
from slackwrap.analytics.rollups import compute_rollups as _compute_rollups
from slackwrap.db import Database


class AnalyticsEngine:
    def __init__(self, db: Database):
        self.db = db

    def volume(self, you_id: int, them_id: int, filters: Filters) -> VolumeStats:
        return compute_volume(self.db, you_id, them_id, filters)

    def huddles(self, you_id: int, them_id: int, filters: Filters) -> HuddleStats:
        return compute_huddles(self.db, you_id, them_id, filters)

    def response_times(self, you_id: int, them_id: int, filters: Filters) -> ResponseTimeStats:
        return compute_response_times(self.db, you_id, them_id, filters)

    def threads(self, you_id: int, them_id: int, filters: Filters) -> ThreadStats:
        return compute_threads(self.db, you_id, them_id, filters)

    def communication(self, you_id: int, them_id: int, filters: Filters) -> CommunicationStats:
        return compute_communication(self.db, you_id, them_id, filters)

    def streaks(self, you_id: int, them_id: int, filters: Filters) -> StreakStats:
        return compute_streaks(self.db, you_id, them_id, filters)

    def trends(self, you_id: int, them_id: int, filters: Filters) -> TrendStats:
        return compute_trends(self.db, you_id, them_id, filters)

    def heatmap(self, you_id: int, them_id: int, filters: Filters) -> HeatmapResult:
        return compute_heatmap(self.db, you_id, them_id, filters)

    def relationship(self, you_id: int, them_id: int, filters: Filters) -> RelationshipStats:
        return compute_relationship(self.db, you_id, them_id, filters)

    def compute_rollups(self, you_id: int, them_id: int, relationship_key: str) -> None:
        _compute_rollups(self.db, you_id, them_id, relationship_key)

    def text_search(self, query: str, limit: int = 50) -> list[dict]:
        rows = self.db.execute(
            """
            SELECT m.id, m.user_id, m.text, m.created_at, m.channel_id, m.slack_ts
            FROM messages m
            JOIN messages_fts ON messages_fts.rowid = m.id
            WHERE messages_fts MATCH ?
            ORDER BY m.created_at DESC LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def raw_sql(self, query: str, params: tuple = ()) -> QueryResult:
        cursor = self.db.execute(query, params)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return QueryResult(rows=[dict(r) for r in rows], columns=columns, row_count=len(rows))
