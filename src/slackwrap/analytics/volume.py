from __future__ import annotations

from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import VolumeStats
from slackwrap.db import Database

SYSTEM_SUBTYPES = (
    "huddle_thread",
    "channel_join",
    "channel_leave",
    "channel_topic",
    "channel_purpose",
    "channel_name",
    "bot_message",
    "bot_add",
    "bot_remove",
    "file_comment",
    "file_mention",
    "pinned_item",
    "unpinned_item",
    "group_join",
    "group_leave",
    "group_topic",
    "group_purpose",
    "group_name",
    "channel_archive",
    "channel_unarchive",
    "ekm_access_denied",
    "reminder_add",
    "sh_room_created",
    "tombstone",
)


def _system_subtype_clause(alias: str = "m") -> str:
    placeholders = ", ".join("?" for _ in SYSTEM_SUBTYPES)
    return f"({alias}.subtype IS NULL OR {alias}.subtype NOT IN ({placeholders}))"


def compute_volume(
    db: Database,
    you_id: int,
    them_id: int,
    filters: Filters,
) -> VolumeStats:
    where, params = build_where(filters)
    base = f"""
        FROM messages m
        {where}
        {"AND" if where else "WHERE"} {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    base_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    row = db.execute(
        f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as you_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as them_count,
            MIN(m.created_at) as first_ts,
            MAX(m.created_at) as last_ts
        {base}
    """,
        tuple([you_id, them_id] + base_params),
    ).fetchone()

    total = row["total"]
    if total == 0:
        return VolumeStats()

    you_count = row["you_count"]
    them_count = row["them_count"]
    first_ts = row["first_ts"]
    last_ts = row["last_ts"]
    total_days = max(int((last_ts - first_ts) / 86400) + 1, 1)
    per_week = total / max(total_days / 7, 1)

    busiest = db.execute(
        f"""
        SELECT date(m.created_at, 'unixepoch') as day, COUNT(*) as cnt
        {base}
        GROUP BY day ORDER BY cnt DESC LIMIT 1
    """,
        tuple(base_params),
    ).fetchone()

    daily = db.execute(
        f"""
        SELECT
            date(m.created_at, 'unixepoch') as day,
            CAST(strftime('%w', m.created_at, 'unixepoch') AS INTEGER) as dow
        {base}
        GROUP BY day
    """,
        tuple(base_params),
    ).fetchall()

    active_days = len(daily)

    wk_split = db.execute(
        f"""
        SELECT
            CASE WHEN CAST(strftime('%w', m.created_at, 'unixepoch') AS INTEGER) IN (0, 6)
                 THEN 'weekend' ELSE 'weekday' END as period,
            COUNT(*) as cnt
        {base}
        GROUP BY period
    """,
        tuple(base_params),
    ).fetchall()

    weekday_msgs = 0
    weekend_msgs = 0
    for r in wk_split:
        if r["period"] == "weekend":
            weekend_msgs = r["cnt"]
        else:
            weekday_msgs = r["cnt"]

    monthly_rows = db.execute(
        f"""
        SELECT strftime('%Y-%m', m.created_at, 'unixepoch') as month, COUNT(*) as cnt
        {base}
        GROUP BY month ORDER BY month
    """,
        tuple(base_params),
    ).fetchall()
    monthly_volumes = {r["month"]: r["cnt"] for r in monthly_rows}

    sorted_months = sorted(monthly_volumes.items(), key=lambda x: x[1], reverse=True)
    monthly_rank = [(m, c, i + 1) for i, (m, c) in enumerate(sorted_months)]

    return VolumeStats(
        total_messages=total,
        you_count=you_count,
        them_count=them_count,
        you_pct=round(you_count / total * 100, 1),
        them_pct=round(them_count / total * 100, 1),
        per_week=round(per_week, 1),
        busiest_day_date=busiest["day"] if busiest else "",
        busiest_day_count=busiest["cnt"] if busiest else 0,
        active_days=active_days,
        total_days=total_days,
        weekday_count=weekday_msgs,
        weekend_count=weekend_msgs,
        messages_per_active_day=round(total / active_days, 1) if active_days else 0.0,
        monthly_volumes=monthly_volumes,
        monthly_rank=monthly_rank,
    )
