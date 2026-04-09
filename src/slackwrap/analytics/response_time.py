from __future__ import annotations
from datetime import datetime, timezone
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import ResponseTimeStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database

MAX_GAP_SECONDS = 4 * 3600

def _median(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2

def _build_turns(messages: list[dict]) -> list[dict]:
    if not messages:
        return []
    turns = []
    current = {"user_id": messages[0]["user_id"], "start_ts": messages[0]["created_at"]}
    for msg in messages[1:]:
        if msg["user_id"] == current["user_id"]:
            pass
        else:
            turns.append(current)
            current = {"user_id": msg["user_id"], "start_ts": msg["created_at"]}
    turns.append(current)
    return turns

def compute_response_times(db: Database, you_id: int, them_id: int, filters: Filters) -> ResponseTimeStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"{base_where} AND {_system_subtype_clause()} AND m.user_id IN (?, ?)"
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    rows = db.execute(f"SELECT m.user_id, m.created_at FROM messages m {full_where} ORDER BY m.created_at", tuple(full_params)).fetchall()

    if len(rows) < 2:
        return ResponseTimeStats()

    messages = [{"user_id": r["user_id"], "created_at": r["created_at"]} for r in rows]
    turns = _build_turns(messages)

    your_times: list[int] = []
    their_times: list[int] = []
    by_hour_raw: dict[int, list[int]] = {}

    for i in range(1, len(turns)):
        prev, curr = turns[i - 1], turns[i]
        delta = int(curr["start_ts"] - prev["start_ts"])
        if delta >= MAX_GAP_SECONDS:
            continue
        hour = datetime.fromtimestamp(curr["start_ts"], tz=timezone.utc).hour
        if prev["user_id"] != you_id and curr["user_id"] == you_id:
            your_times.append(delta)
        elif prev["user_id"] == you_id and curr["user_id"] != you_id:
            their_times.append(delta)
        if prev["user_id"] != curr["user_id"]:
            by_hour_raw.setdefault(hour, []).append(delta)

    by_hour = {h: _median(ts) for h, ts in sorted(by_hour_raw.items()) if len(ts) >= 3}
    fastest_hour = min(by_hour, key=by_hour.get) if by_hour else 0
    slowest_hour = max(by_hour, key=by_hour.get) if by_hour else 0

    monthly_raw: dict[str, list[int]] = {}
    for i in range(1, len(turns)):
        prev, curr = turns[i - 1], turns[i]
        delta = int(curr["start_ts"] - prev["start_ts"])
        if delta >= MAX_GAP_SECONDS or prev["user_id"] == curr["user_id"]:
            continue
        month = datetime.fromtimestamp(curr["start_ts"], tz=timezone.utc).strftime("%Y-%m")
        monthly_raw.setdefault(month, []).append(delta)
    monthly_trend = {m: _median(ts) for m, ts in sorted(monthly_raw.items()) if len(ts) >= 3}

    return ResponseTimeStats(
        your_median=_median(your_times),
        your_avg=int(sum(your_times) / len(your_times)) if your_times else 0,
        their_median=_median(their_times),
        their_avg=int(sum(their_times) / len(their_times)) if their_times else 0,
        fastest_hour=fastest_hour, fastest_hour_median=by_hour.get(fastest_hour, 0),
        slowest_hour=slowest_hour, slowest_hour_median=by_hour.get(slowest_hour, 0),
        by_hour=by_hour, monthly_trend=monthly_trend,
    )
