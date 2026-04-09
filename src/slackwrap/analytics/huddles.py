from __future__ import annotations
from slackwrap.analytics.filters import Filters
from slackwrap.analytics.types import HuddleStats
from slackwrap.db import Database

DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

def _median(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2

def compute_huddles(db: Database, you_id: int, them_id: int, filters: Filters) -> HuddleStats:
    channel_clause = ""
    params: list = []
    if filters.channel_id is not None:
        channel_clause = "WHERE h.channel_id = ?"
        params.append(filters.channel_id)

    rows = db.execute(f"""
        SELECT h.duration_seconds, h.created_by_user_id, h.started_at,
               CAST(strftime('%w', h.started_at, 'unixepoch') AS INTEGER) as dow
        FROM huddles h
        {channel_clause}
    """, tuple(params)).fetchall()

    if not rows:
        return HuddleStats()

    durations = [r["duration_seconds"] for r in rows]
    total_seconds = sum(durations)
    total_huddles = len(rows)
    started_by_you = sum(1 for r in rows if r["created_by_user_id"] == you_id)
    started_by_them = sum(1 for r in rows if r["created_by_user_id"] == them_id)

    weekday_breakdown: dict[str, int] = {}
    for r in rows:
        day_name = DAY_NAMES[r["dow"]]
        weekday_breakdown[day_name] = weekday_breakdown.get(day_name, 0) + 1

    first_ts = min(r["started_at"] for r in rows)
    last_ts = max(r["started_at"] for r in rows)
    span_days = max(int((last_ts - first_ts) / 86400) + 1, 1)
    per_week = round(total_huddles / max(span_days / 7, 1), 1)
    per_month = round(total_huddles / max(span_days / 30, 1), 1)

    return HuddleStats(
        total_huddles=total_huddles, total_seconds=total_seconds,
        avg_seconds=total_seconds // total_huddles,
        median_seconds=_median(durations),
        longest_seconds=max(durations), shortest_seconds=min(durations),
        started_by_you=started_by_you, started_by_them=started_by_them,
        weekday_breakdown=weekday_breakdown, per_week=per_week, per_month=per_month,
        huddle_to_message_ratio=0.0,
    )
