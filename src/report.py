from datetime import datetime, timezone
from typing import Callable


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes:02d}m"


def compute_stats(huddles: list[dict], user_id: str) -> dict:
    user_huddles = [
        h for h in huddles
        if user_id in h["room"]["participant_history"]
    ]
    if not user_huddles:
        return {
            "total_huddles": 0,
            "total_seconds": 0,
            "avg_seconds": 0,
            "longest_seconds": 0,
            "shortest_seconds": 0,
            "huddles": [],
        }
    durations = [
        h["room"]["date_end"] - h["room"]["date_start"]
        for h in user_huddles
    ]
    return {
        "total_huddles": len(user_huddles),
        "total_seconds": sum(durations),
        "avg_seconds": sum(durations) // len(durations),
        "longest_seconds": max(durations),
        "shortest_seconds": min(durations),
        "huddles": user_huddles,
    }


def format_report(stats: dict, channel_label: str, resolve_name: Callable[[str], str]) -> str:
    if stats["total_huddles"] == 0:
        return f"\nHuddle Time Report\n==================\nChannel: {channel_label}\n\nNo huddles found.\n"

    lines = []
    lines.append("")
    lines.append("Huddle Time Report")
    lines.append("=" * 40)
    lines.append(f"Channel: {channel_label}")

    huddles = stats["huddles"]
    all_timestamps = [h["room"]["date_start"] for h in huddles]
    first_date = datetime.fromtimestamp(min(all_timestamps), tz=timezone.utc).astimezone()
    last_date = datetime.fromtimestamp(max(all_timestamps), tz=timezone.utc).astimezone()
    lines.append(f"Period:  {first_date.strftime('%Y-%m-%d')} -> {last_date.strftime('%Y-%m-%d')}")
    lines.append(f"Total huddles: {stats['total_huddles']}")
    lines.append("")
    lines.append(f"{'Date':<13}{'Started By':<18}{'Duration'}")
    lines.append("-" * 40)

    sorted_huddles = sorted(huddles, key=lambda h: h["room"]["date_start"])
    for h in sorted_huddles:
        room = h["room"]
        dt = datetime.fromtimestamp(room["date_start"], tz=timezone.utc).astimezone()
        date_str = dt.strftime("%Y-%m-%d")
        started_by = resolve_name(room["created_by"])
        duration = format_duration(room["date_end"] - room["date_start"])
        lines.append(f"{date_str:<13}{started_by:<18}{duration}")

    lines.append("")
    lines.append("Summary")
    lines.append("-" * 40)
    lines.append(f"Total time:      {format_duration(stats['total_seconds'])}")
    lines.append(f"Avg per huddle:  {format_duration(stats['avg_seconds'])}")
    lines.append(f"Longest huddle:  {format_duration(stats['longest_seconds'])}")
    lines.append(f"Shortest huddle: {format_duration(stats['shortest_seconds'])}")
    lines.append("")

    return "\n".join(lines)
