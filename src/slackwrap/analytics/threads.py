from __future__ import annotations

from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import ThreadStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_threads(
    db: Database,
    you_id: int,
    them_id: int,
    filters: Filters,
) -> ThreadStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"{base_where} AND {_system_subtype_clause()} AND m.user_id IN (?, ?)"
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    # Total messages
    total_row = db.execute(
        f"SELECT COUNT(*) as total FROM messages m {full_where}",
        tuple(full_params),
    ).fetchone()
    total = total_row["total"]
    if total == 0:
        return ThreadStats()

    # Top-level: thread_ts is NULL or thread_ts == slack_ts
    top_level_row = db.execute(
        f"""SELECT COUNT(*) as cnt FROM messages m {full_where}
            AND (m.thread_ts IS NULL OR m.thread_ts = m.slack_ts)""",
        tuple(full_params),
    ).fetchone()
    top_level = top_level_row["cnt"]
    in_threads = total - top_level

    # Thread parents: messages with reply_count > 0 (these are the actual thread starters)
    thread_parents = db.execute(
        f"""SELECT m.user_id, m.reply_count FROM messages m {full_where}
            AND m.reply_count > 0""",
        tuple(full_params),
    ).fetchall()

    started_by_you = 0
    started_by_them = 0
    depths: list[int] = []
    for tp in thread_parents:
        if tp["user_id"] == you_id:
            started_by_you += 1
        elif tp["user_id"] == them_id:
            started_by_them += 1
        depths.append(tp["reply_count"])

    deepest = max(depths) if depths else 0
    avg_depth = sum(depths) / len(depths) if depths else 0.0
    thread_pct = round(in_threads / total * 100, 1) if total else 0.0

    return ThreadStats(
        total_messages=total,
        top_level=top_level,
        in_threads=in_threads,
        thread_pct=thread_pct,
        threads_started_by_you=started_by_you,
        threads_started_by_them=started_by_them,
        deepest_thread=deepest,
        avg_thread_depth=round(avg_depth, 1),
    )
