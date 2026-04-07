from collections import Counter
from datetime import datetime, timezone
from typing import Callable


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes:02d}m" if parts else f"{minutes}m")
    return " ".join(parts) if parts else "0m"


def extract_huddles(messages: list[dict]) -> list[dict]:
    huddles = []
    for msg in messages:
        if msg.get("subtype") != "huddle_thread":
            continue
        room = msg.get("room", {})
        if not room.get("has_ended"):
            continue
        huddles.append(msg)
    return huddles


def compute_stats(huddles: list[dict], user_id: str, target_user_id: str | None = None) -> dict:
    user_huddles = [
        h for h in huddles
        if user_id in h["room"]["participant_history"]
    ]
    if target_user_id:
        user_huddles = [
            h for h in user_huddles
            if target_user_id in h["room"]["participant_history"]
        ]
    if not user_huddles:
        return {
            "total_huddles": 0,
            "total_seconds": 0,
            "avg_seconds": 0,
            "longest_seconds": 0,
            "shortest_seconds": 0,
            "median_seconds": 0,
            "huddles": [],
            "started_by_you": 0,
            "started_by_them": 0,
            "monthly_breakdown": {},
            "weekday_breakdown": {},
        }
    durations = [
        h["room"]["date_end"] - h["room"]["date_start"]
        for h in user_huddles
    ]
    sorted_durations = sorted(durations)
    n = len(sorted_durations)
    if n % 2 == 1:
        median = sorted_durations[n // 2]
    else:
        median = (sorted_durations[n // 2 - 1] + sorted_durations[n // 2]) // 2

    started_by_you = sum(1 for h in user_huddles if h["room"]["created_by"] == user_id)

    monthly: Counter[str] = Counter()
    weekday: Counter[str] = Counter()
    for h in user_huddles:
        dt = datetime.fromtimestamp(h["room"]["date_start"], tz=timezone.utc).astimezone()
        monthly[dt.strftime("%Y-%m")] += 1
        weekday[dt.strftime("%A")] += 1

    return {
        "total_huddles": len(user_huddles),
        "total_seconds": sum(durations),
        "avg_seconds": sum(durations) // len(durations),
        "longest_seconds": max(durations),
        "shortest_seconds": min(durations),
        "median_seconds": median,
        "huddles": user_huddles,
        "started_by_you": started_by_you,
        "started_by_them": len(user_huddles) - started_by_you,
        "monthly_breakdown": dict(sorted(monthly.items())),
        "weekday_breakdown": dict(weekday),
    }


def format_report(stats: dict, channel_label: str, resolve_name: Callable[[str], str]) -> str:
    if stats["total_huddles"] == 0:
        return f"\nHuddle Time Report\n==================\nChannel: {channel_label}\n\nNo huddles found.\n"

    lines = []
    lines.append("")
    lines.append("Huddle Time Report")
    lines.append("=" * 50)
    lines.append(f"Channel:  {channel_label}")

    huddles = stats["huddles"]
    all_timestamps = [h["room"]["date_start"] for h in huddles]
    first_date = datetime.fromtimestamp(min(all_timestamps), tz=timezone.utc).astimezone()
    last_date = datetime.fromtimestamp(max(all_timestamps), tz=timezone.utc).astimezone()
    span_days = (last_date - first_date).days + 1
    lines.append(f"Period:   {first_date.strftime('%Y-%m-%d')} -> {last_date.strftime('%Y-%m-%d')} ({span_days} days)")
    lines.append("")

    # Time overview
    lines.append("Time Overview")
    lines.append("-" * 50)
    total_hrs = stats['total_seconds'] / 3600
    lines.append(f"  Total time:       {format_duration(stats['total_seconds'])} ({total_hrs:.1f} hours)")
    lines.append(f"  Total huddles:    {stats['total_huddles']}")
    avg_hrs = stats['avg_seconds'] / 3600
    lines.append(f"  Average:          {format_duration(stats['avg_seconds'])} per huddle ({avg_hrs:.1f} hrs)")
    lines.append(f"  Median:           {format_duration(stats['median_seconds'])} per huddle")
    lines.append(f"  Longest:          {format_duration(stats['longest_seconds'])}")
    lines.append(f"  Shortest:         {format_duration(stats['shortest_seconds'])}")

    # Frequency
    weeks = max(span_days / 7, 1)
    months = max(span_days / 30, 1)
    lines.append("")
    lines.append("Frequency")
    lines.append("-" * 50)
    lines.append(f"  Per week:         {stats['total_huddles'] / weeks:.1f} huddles ({format_duration(int(stats['total_seconds'] / weeks))})")
    lines.append(f"  Per month:        {stats['total_huddles'] / months:.1f} huddles ({format_duration(int(stats['total_seconds'] / months))})")

    # Who initiates
    lines.append("")
    lines.append("Who Starts Huddles")
    lines.append("-" * 50)
    total = stats["total_huddles"]
    you_pct = (stats["started_by_you"] / total) * 100
    them_pct = (stats["started_by_them"] / total) * 100
    lines.append(f"  You:              {stats['started_by_you']} ({you_pct:.0f}%)")
    lines.append(f"  Them:             {stats['started_by_them']} ({them_pct:.0f}%)")

    # Busiest day of week
    weekday = stats.get("weekday_breakdown", {})
    if weekday:
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        sorted_days = sorted(weekday.items(), key=lambda x: day_order.index(x[0]) if x[0] in day_order else 7)
        lines.append("")
        lines.append("By Day of Week")
        lines.append("-" * 50)
        for day, count in sorted_days:
            lines.append(f"  {day:<12} {count:>5}")

    lines.append("")
    return "\n".join(lines)
