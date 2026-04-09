from __future__ import annotations

import calendar
import time
from datetime import datetime, timezone

from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import TrendStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_trends(
    db: Database,
    you_id: int,
    them_id: int,
    filters: Filters,
) -> TrendStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"{base_where} AND {_system_subtype_clause()} AND m.user_id IN (?, ?)"
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    now = time.time()

    # -- 30-day rolling window --
    last_30d_start = now - 30 * 86400
    prev_30d_start = now - 60 * 86400

    last_30d_row = db.execute(
        f"""
        SELECT COUNT(*) as cnt FROM messages m
        {full_where} AND m.created_at >= ? AND m.created_at < ?
        """,
        tuple(full_params + [last_30d_start, now]),
    ).fetchone()
    last_30d_count = last_30d_row["cnt"]

    prev_30d_row = db.execute(
        f"""
        SELECT COUNT(*) as cnt FROM messages m
        {full_where} AND m.created_at >= ? AND m.created_at < ?
        """,
        tuple(full_params + [prev_30d_start, last_30d_start]),
    ).fetchone()
    prev_30d_count = prev_30d_row["cnt"]

    if prev_30d_count > 0:
        pct_change_30d = round((last_30d_count - prev_30d_count) / prev_30d_count * 100, 1)
    elif last_30d_count > 0:
        pct_change_30d = 100.0
    else:
        pct_change_30d = None

    # -- Current month --
    now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
    current_month_str = now_dt.strftime("%Y-%m")
    month_start = datetime(now_dt.year, now_dt.month, 1, tzinfo=timezone.utc).timestamp()

    current_month_row = db.execute(
        f"""
        SELECT COUNT(*) as cnt FROM messages m
        {full_where} AND m.created_at >= ? AND m.created_at < ?
        """,
        tuple(full_params + [month_start, now]),
    ).fetchone()
    current_month_count = current_month_row["cnt"]

    # -- Year-over-Year with daily rate normalization --
    yoy_month = ""
    yoy_count: int | None = None
    yoy_pct_change: float | None = None

    last_year = now_dt.year - 1
    same_month_last_year = now_dt.month
    try:
        ly_start = datetime(last_year, same_month_last_year, 1, tzinfo=timezone.utc)
        _, ly_days = calendar.monthrange(last_year, same_month_last_year)
        ly_end_ts = datetime(last_year, same_month_last_year, ly_days, 23, 59, 59, tzinfo=timezone.utc).timestamp() + 1

        yoy_row = db.execute(
            f"""
            SELECT COUNT(*) as cnt FROM messages m
            {full_where} AND m.created_at >= ? AND m.created_at < ?
            """,
            tuple(full_params + [ly_start.timestamp(), ly_end_ts]),
        ).fetchone()

        yoy_count = yoy_row["cnt"]
        yoy_month = ly_start.strftime("%Y-%m")

        # Normalize by daily rate
        _, current_month_days = calendar.monthrange(now_dt.year, now_dt.month)
        days_elapsed = now_dt.day
        if days_elapsed > 0 and current_month_count > 0:
            current_daily_rate = current_month_count / days_elapsed
            current_projected = current_daily_rate * current_month_days
        else:
            current_projected = current_month_count

        if yoy_count and yoy_count > 0:
            ly_daily_rate = yoy_count / ly_days
            if ly_daily_rate > 0:
                yoy_pct_change = round(
                    (current_projected / current_month_days - ly_daily_rate) / ly_daily_rate * 100,
                    1,
                )
    except (ValueError, OverflowError):
        pass

    return TrendStats(
        last_30d_count=last_30d_count,
        prev_30d_count=prev_30d_count,
        pct_change_30d=pct_change_30d,
        current_month=current_month_str,
        current_month_count=current_month_count,
        yoy_month=yoy_month,
        yoy_count=yoy_count,
        yoy_pct_change=yoy_pct_change,
    )
