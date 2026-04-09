from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone

DAY_TO_WEEKDAY_NUM = {
    "Sunday": "0",
    "Monday": "1",
    "Tuesday": "2",
    "Wednesday": "3",
    "Thursday": "4",
    "Friday": "5",
    "Saturday": "6",
}


@dataclass
class Filters:
    relationship_key: str | None = None
    user_id: int | None = None
    channel_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    day_of_week: str | None = None
    hour: int | None = None
    subtype: str | None = None
    has_reactions: bool | None = None
    has_files: bool | None = None
    in_thread: bool | None = None


def build_where(filters: Filters, table_alias: str = "m") -> tuple[str, list]:
    conditions: list[str] = []
    params: list = []
    a = table_alias

    if filters.relationship_key:
        parts = filters.relationship_key.split(":")
        if len(parts) == 2:
            uid1, uid2 = int(parts[0]), int(parts[1])
            conditions.append(f"{a}.user_id IN (?, ?)")
            params.extend([uid1, uid2])

    if filters.user_id is not None:
        conditions.append(f"{a}.user_id = ?")
        params.append(filters.user_id)

    if filters.channel_id is not None:
        conditions.append(f"{a}.channel_id = ?")
        params.append(filters.channel_id)

    if filters.date_from is not None:
        ts = datetime(
            filters.date_from.year,
            filters.date_from.month,
            filters.date_from.day,
            tzinfo=timezone.utc,
        ).timestamp()
        conditions.append(f"{a}.created_at >= ?")
        params.append(ts)

    if filters.date_to is not None:
        next_day = (
            datetime(
                filters.date_to.year,
                filters.date_to.month,
                filters.date_to.day,
                tzinfo=timezone.utc,
            ).timestamp()
            + 86400
        )
        conditions.append(f"{a}.created_at < ?")
        params.append(next_day)

    if filters.day_of_week is not None:
        weekday_num = DAY_TO_WEEKDAY_NUM.get(filters.day_of_week)
        if weekday_num is not None:
            conditions.append(
                f"strftime('%w', {a}.created_at, 'unixepoch') = ?"
            )
            params.append(weekday_num)

    if filters.hour is not None:
        conditions.append(
            f"CAST(strftime('%H', {a}.created_at, 'unixepoch', 'localtime') AS INTEGER) = ?"
        )
        params.append(filters.hour)

    if filters.subtype is not None:
        conditions.append(f"{a}.subtype = ?")
        params.append(filters.subtype)

    if filters.has_reactions is True:
        conditions.append(
            f"EXISTS (SELECT 1 FROM reactions r WHERE r.message_id = {a}.id)"
        )

    if filters.has_files is True:
        conditions.append(f"{a}.files_count > 0")

    if filters.in_thread is True:
        conditions.append(
            f"{a}.thread_ts IS NOT NULL AND {a}.thread_ts != {a}.slack_ts"
        )
    elif filters.in_thread is False:
        conditions.append(
            f"({a}.thread_ts IS NULL OR {a}.thread_ts = {a}.slack_ts)"
        )

    if not conditions:
        return "", []
    return "WHERE " + " AND ".join(conditions), params
