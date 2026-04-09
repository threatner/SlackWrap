from __future__ import annotations

from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import HeatmapResult
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
HOUR_LABELS = [f"{h:02d}:00" for h in range(24)]

# SQLite strftime('%w') returns 0=Sunday, 1=Monday, ..., 6=Saturday
# We want Monday=0 .. Sunday=6, so map: (sqlite_dow + 6) % 7
_SQLITE_DOW_TO_ISO = {
    0: 6,  # Sunday -> 6
    1: 0,  # Monday -> 0
    2: 1,  # Tuesday -> 1
    3: 2,  # Wednesday -> 2
    4: 3,  # Thursday -> 3
    5: 4,  # Friday -> 4
    6: 5,  # Saturday -> 5
}


def compute_heatmap(
    db: Database,
    you_id: int,
    them_id: int,
    filters: Filters,
) -> HeatmapResult:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"{base_where} AND {_system_subtype_clause()} AND m.user_id IN (?, ?)"
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    rows = db.execute(
        f"""
        SELECT
            CAST(strftime('%w', m.created_at, 'unixepoch') AS INTEGER) as dow,
            CAST(strftime('%H', m.created_at, 'unixepoch') AS INTEGER) as hour,
            COUNT(*) as cnt
        FROM messages m
        {full_where}
        GROUP BY dow, hour
        """,
        tuple(full_params),
    ).fetchall()

    data: dict[int, dict[int, int]] = {}
    for row in rows:
        iso_dow = _SQLITE_DOW_TO_ISO[row["dow"]]
        hour = row["hour"]
        if iso_dow not in data:
            data[iso_dow] = {}
        data[iso_dow][hour] = data[iso_dow].get(hour, 0) + row["cnt"]

    return HeatmapResult(
        data=data,
        x_labels=DAY_NAMES,
        y_labels=HOUR_LABELS,
    )
