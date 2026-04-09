from __future__ import annotations

from datetime import datetime, timezone

from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import StreakStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database

MILESTONE_THRESHOLDS = [100, 500, 1_000, 5_000, 10_000, 50_000, 100_000]


def compute_streaks(
    db: Database,
    you_id: int,
    them_id: int,
    filters: Filters,
) -> StreakStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"{base_where} AND {_system_subtype_clause()} AND m.user_id IN (?, ?)"
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    rows = db.execute(
        f"SELECT m.created_at FROM messages m {full_where} ORDER BY m.created_at",
        tuple(full_params),
    ).fetchall()

    if not rows:
        return StreakStats()

    timestamps = [r["created_at"] for r in rows]

    # Build set of active dates (UTC)
    active_dates: set[int] = set()
    for ts in timestamps:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        active_dates.add(dt.toordinal())

    sorted_dates = sorted(active_dates)

    # Longest consecutive day streak
    longest_streak = 1
    longest_start = sorted_dates[0]
    longest_end = sorted_dates[0]
    current_streak = 1
    current_start = sorted_dates[0]

    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] == sorted_dates[i - 1] + 1:
            current_streak += 1
        else:
            if current_streak > longest_streak:
                longest_streak = current_streak
                longest_start = current_start
                longest_end = sorted_dates[i - 1]
            current_streak = 1
            current_start = sorted_dates[i]

    if current_streak > longest_streak:
        longest_streak = current_streak
        longest_start = current_start
        longest_end = sorted_dates[-1]

    # Current streak from last date backwards
    curr_streak = 1
    for i in range(len(sorted_dates) - 1, 0, -1):
        if sorted_dates[i] == sorted_dates[i - 1] + 1:
            curr_streak += 1
        else:
            break

    # Convert ordinals back to timestamps for start/end
    def ordinal_to_ts(ordinal: int) -> float:
        dt = datetime.fromordinal(ordinal).replace(tzinfo=timezone.utc)
        return dt.timestamp()

    # Longest gap between consecutive messages
    longest_gap = 0
    gap_start_ts = 0.0
    gap_end_ts = 0.0
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i - 1]
        if gap > longest_gap:
            longest_gap = gap
            gap_start_ts = timestamps[i - 1]
            gap_end_ts = timestamps[i]

    # Milestones: check which message count thresholds have been hit
    total = len(timestamps)
    milestones: dict[str, str] = {}
    for threshold in MILESTONE_THRESHOLDS:
        if total >= threshold:
            # Find the timestamp of the Nth message
            milestone_ts = timestamps[threshold - 1]
            dt = datetime.fromtimestamp(milestone_ts, tz=timezone.utc)
            milestones[str(threshold)] = dt.strftime("%Y-%m-%d")

    return StreakStats(
        longest_streak_days=longest_streak,
        longest_streak_start=ordinal_to_ts(longest_start),
        longest_streak_end=ordinal_to_ts(longest_end),
        current_streak_days=curr_streak,
        longest_gap_seconds=int(longest_gap),
        longest_gap_start=gap_start_ts,
        longest_gap_end=gap_end_ts,
        milestones=milestones,
    )
