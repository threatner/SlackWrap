from __future__ import annotations

from slackwrap.analytics.filters import Filters
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def sample_messages(
    db: Database,
    user_id: int,
    channel_id: int | None = None,
    per_month: int = 5,
) -> list[dict]:
    """Stratified sampling of messages by month, evenly spaced within each month."""
    sys_clause = _system_subtype_clause()
    sys_params = list(SYSTEM_SUBTYPES)

    where_parts = [sys_clause, "m.user_id = ?"]
    params: list = sys_params + [user_id]

    if channel_id is not None:
        where_parts.append("m.channel_id = ?")
        params.append(channel_id)

    where = "WHERE " + " AND ".join(where_parts)

    # Get distinct months
    months = db.execute(
        f"""
        SELECT DISTINCT strftime('%Y-%m', m.created_at, 'unixepoch') as month
        FROM messages m {where}
        ORDER BY month
        """,
        tuple(params),
    ).fetchall()

    samples: list[dict] = []
    for month_row in months:
        month = month_row["month"]
        # Fetch all messages for this month
        rows = db.execute(
            f"""
            SELECT m.id, m.user_id, m.text, m.created_at, m.channel_id, m.slack_ts
            FROM messages m {where}
            AND strftime('%Y-%m', m.created_at, 'unixepoch') = ?
            ORDER BY m.created_at
            """,
            tuple(params + [month]),
        ).fetchall()

        if not rows:
            continue

        # Evenly spaced sampling
        total = len(rows)
        count = min(per_month, total)
        if count == total:
            indices = list(range(total))
        else:
            step = total / count
            indices = [int(i * step) for i in range(count)]

        for idx in indices:
            row = rows[idx]
            samples.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "text": row["text"],
                "created_at": row["created_at"],
                "channel_id": row["channel_id"],
                "slack_ts": row["slack_ts"],
                "month": month,
            })

    return samples


def sample_conversation_windows(
    db: Database,
    channel_id: int,
    window_size: int = 10,
    stride: int = 5,
) -> list[dict]:
    """Sliding window over conversation messages for embedding context."""
    sys_clause = _system_subtype_clause()
    sys_params = list(SYSTEM_SUBTYPES)

    rows = db.execute(
        f"""
        SELECT m.id, m.user_id, m.text, m.created_at, m.slack_ts
        FROM messages m
        WHERE {sys_clause}
        AND m.channel_id = ?
        AND m.text IS NOT NULL AND m.text != ''
        ORDER BY m.created_at
        """,
        tuple(sys_params + [channel_id]),
    ).fetchall()

    windows: list[dict] = []
    i = 0
    while i < len(rows):
        window_rows = rows[i:i + window_size]
        messages = [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "text": r["text"],
                "created_at": r["created_at"],
                "slack_ts": r["slack_ts"],
            }
            for r in window_rows
        ]
        windows.append({
            "start_ts": window_rows[0]["created_at"],
            "end_ts": window_rows[-1]["created_at"],
            "messages": messages,
        })
        i += stride

    return windows


def build_stats_summary(
    engine,
    you_id: int,
    them_id: int,
) -> dict:
    """Build a compact stats dictionary from the analytics engine for prompt context."""
    filters = Filters()

    summary: dict = {}

    # Volume
    vol = engine.volume(you_id, them_id, filters)
    summary["total_messages"] = vol.total_messages
    summary["you_count"] = vol.you_count
    summary["them_count"] = vol.them_count
    summary["you_pct"] = vol.you_pct
    summary["them_pct"] = vol.them_pct
    summary["per_week"] = vol.per_week
    summary["active_days"] = vol.active_days
    summary["total_days"] = vol.total_days
    summary["busiest_day_date"] = vol.busiest_day_date
    summary["busiest_day_count"] = vol.busiest_day_count
    summary["weekday_count"] = vol.weekday_count
    summary["weekend_count"] = vol.weekend_count

    # Communication style
    comm = engine.communication(you_id, them_id, filters)
    summary["your_avg_words"] = comm.your_avg_words
    summary["their_avg_words"] = comm.their_avg_words
    summary["your_emoji_total"] = comm.your_emoji_total
    summary["their_emoji_total"] = comm.their_emoji_total
    summary["your_top_words"] = comm.your_top_words[:5]
    summary["their_top_words"] = comm.their_top_words[:5]
    summary["your_reactions_given"] = comm.your_reactions_given
    summary["their_reactions_given"] = comm.their_reactions_given

    # Streaks
    streaks = engine.streaks(you_id, them_id, filters)
    summary["longest_streak"] = streaks.longest_streak_days
    summary["current_streak"] = streaks.current_streak_days

    # Response times
    rt = engine.response_times(you_id, them_id, filters)
    summary["your_avg_response_seconds"] = rt.your_avg
    summary["their_avg_response_seconds"] = rt.their_avg

    return summary
