from __future__ import annotations

from slackwrap.analytics.volume import SYSTEM_SUBTYPES
from slackwrap.db import Database


def _system_subtype_clause(alias: str = "m") -> str:
    placeholders = ", ".join("?" for _ in SYSTEM_SUBTYPES)
    return f"({alias}.subtype IS NULL OR {alias}.subtype NOT IN ({placeholders}))"


def compute_rollups(
    db: Database,
    you_id: int,
    them_id: int,
    relationship_key: str,
) -> None:
    system_params = list(SYSTEM_SUBTYPES)

    # Weekly rollups
    weekly_rows = db.execute(
        f"""
        SELECT
            date(m.created_at, 'unixepoch', 'weekday 0', '-6 days') as week_start,
            COUNT(*) as message_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as your_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as their_count
        FROM messages m
        WHERE m.user_id IN (?, ?)
          AND {_system_subtype_clause()}
        GROUP BY week_start
        ORDER BY week_start
        """,
        tuple(
            [you_id, them_id, you_id, them_id] + system_params
        ),
    ).fetchall()

    for row in weekly_rows:
        db.execute(
            """
            INSERT INTO weekly_stats (relationship_key, week_start, message_count, your_count, their_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(relationship_key, week_start) DO UPDATE SET
                message_count = excluded.message_count,
                your_count = excluded.your_count,
                their_count = excluded.their_count
            """,
            (
                relationship_key,
                row["week_start"],
                row["message_count"],
                row["your_count"],
                row["their_count"],
            ),
        )

    # Monthly rollups
    monthly_rows = db.execute(
        f"""
        SELECT
            strftime('%Y-%m', m.created_at, 'unixepoch') as month,
            COUNT(*) as message_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as your_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as their_count
        FROM messages m
        WHERE m.user_id IN (?, ?)
          AND {_system_subtype_clause()}
        GROUP BY month
        ORDER BY month
        """,
        tuple(
            [you_id, them_id, you_id, them_id] + system_params
        ),
    ).fetchall()

    for row in monthly_rows:
        db.execute(
            """
            INSERT INTO monthly_stats (relationship_key, month, message_count, your_count, their_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(relationship_key, month) DO UPDATE SET
                message_count = excluded.message_count,
                your_count = excluded.your_count,
                their_count = excluded.their_count
            """,
            (
                relationship_key,
                row["month"],
                row["message_count"],
                row["your_count"],
                row["their_count"],
            ),
        )

    db.commit()
