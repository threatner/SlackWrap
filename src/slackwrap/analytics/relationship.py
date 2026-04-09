from __future__ import annotations

from datetime import datetime, timezone

from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import RelationshipStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_relationship(
    db: Database,
    you_id: int,
    them_id: int,
    filters: Filters,
) -> RelationshipStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"{base_where} AND {_system_subtype_clause()} AND m.user_id IN (?, ?)"
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    # -- Conversation initiations: who sends the first message each day --
    day_first_rows = db.execute(
        f"""
        SELECT date(m.created_at, 'unixepoch') as day, m.user_id, m.created_at
        FROM messages m
        {full_where}
        ORDER BY m.created_at
        """,
        tuple(full_params),
    ).fetchall()

    initiations_you = 0
    initiations_them = 0
    seen_days: set[str] = set()
    for row in day_first_rows:
        day = row["day"]
        if day not in seen_days:
            seen_days.add(day)
            if row["user_id"] == you_id:
                initiations_you += 1
            elif row["user_id"] == them_id:
                initiations_them += 1

    # -- Reciprocity index: min(you_count, them_count) / max(you_count, them_count) --
    counts_row = db.execute(
        f"""
        SELECT
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as you_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as them_count
        FROM messages m
        {full_where}
        """,
        tuple([you_id, them_id] + full_params),
    ).fetchone()

    you_count = counts_row["you_count"] or 0
    them_count = counts_row["them_count"] or 0
    if max(you_count, them_count) > 0:
        reciprocity_index = round(min(you_count, them_count) / max(you_count, them_count), 4)
    else:
        reciprocity_index = 0.0

    # -- First and last message --
    first_row = db.execute(
        f"""
        SELECT m.text, m.created_at, m.user_id
        FROM messages m
        {full_where}
        ORDER BY m.created_at ASC LIMIT 1
        """,
        tuple(full_params),
    ).fetchone()

    last_row = db.execute(
        f"""
        SELECT m.text, m.created_at, m.user_id
        FROM messages m
        {full_where}
        ORDER BY m.created_at DESC LIMIT 1
        """,
        tuple(full_params),
    ).fetchone()

    def _msg_dict(row) -> dict | None:
        if row is None:
            return None
        dt = datetime.fromtimestamp(row["created_at"], tz=timezone.utc)
        return {
            "text": row["text"] or "",
            "created_at": row["created_at"],
            "date": dt.strftime("%Y-%m-%d"),
            "user_id": row["user_id"],
        }

    first_message = _msg_dict(first_row)
    last_message = _msg_dict(last_row)

    # -- Pinned highlights --
    pin_where_parts = []
    pin_params_list: list = []
    if filters.channel_id is not None:
        pin_where_parts.append("p.channel_id = ?")
        pin_params_list.append(filters.channel_id)

    pin_where = "WHERE " + " AND ".join(pin_where_parts) if pin_where_parts else ""

    pin_rows = db.execute(
        f"""
        SELECT p.message_ts, p.pinned_at, p.user_id, p.channel_id,
               m.text as msg_text
        FROM pins p
        LEFT JOIN messages m ON m.slack_ts = p.message_ts AND m.channel_id = p.channel_id
        {pin_where}
        ORDER BY p.pinned_at
        """,
        tuple(pin_params_list),
    ).fetchall()

    pinned_highlights = []
    for row in pin_rows:
        pinned_highlights.append({
            "message_ts": row["message_ts"],
            "pinned_at": row["pinned_at"],
            "user_id": row["user_id"],
            "text": row["msg_text"] or "",
        })

    # -- Shared channel distribution --
    channel_rows = db.execute(
        f"""
        SELECT c.name, COUNT(*) as cnt
        FROM messages m
        JOIN channels c ON c.id = m.channel_id
        {base_where} AND {_system_subtype_clause()} AND m.user_id IN (?, ?)
        GROUP BY c.name
        ORDER BY cnt DESC
        """,
        tuple(params + list(SYSTEM_SUBTYPES) + [you_id, them_id]),
    ).fetchall()

    shared_channel_distribution = {row["name"]: row["cnt"] for row in channel_rows}

    return RelationshipStats(
        reciprocity_index=reciprocity_index,
        conversation_initiations_you=initiations_you,
        conversation_initiations_them=initiations_them,
        first_message=first_message,
        last_message=last_message,
        pinned_highlights=pinned_highlights,
        shared_channel_distribution=shared_channel_distribution,
    )
