from collections import Counter
from datetime import datetime, timezone

from src.report import format_duration

SYSTEM_SUBTYPES = {
    "huddle_thread", "channel_join", "channel_leave", "channel_topic",
    "channel_purpose", "channel_name", "bot_message", "bot_add",
    "bot_remove", "file_share", "file_comment", "file_mention",
    "pinned_item", "unpinned_item", "group_join", "group_leave",
    "group_topic", "group_purpose", "group_name", "channel_archive",
    "channel_unarchive", "ekm_access_denied", "reminder_add",
    "sh_room_created",
}

INITIATION_GAP_SECONDS = 4 * 3600  # 4 hours


def _filter_user_messages(messages: list[dict]) -> list[dict]:
    return [
        m for m in messages
        if m.get("subtype") not in SYSTEM_SUBTYPES
        and m.get("user") is not None
        and m.get("user") != "USLACKBOT"
    ]


def compute_message_stats(messages: list[dict], user_id: str) -> dict:
    user_msgs = _filter_user_messages(messages)

    if not user_msgs:
        return {
            "total_messages": 0,
            "you_count": 0, "them_count": 0,
            "you_pct": 0.0, "them_pct": 0.0,
            "your_avg_words": 0.0, "their_avg_words": 0.0,
            "you_initiated": 0, "them_initiated": 0,
            "your_avg_response_seconds": 0, "their_avg_response_seconds": 0,
            "weekday_breakdown": {}, "hourly_breakdown": {},
            "span_days": 0, "first_ts": 0, "last_ts": 0,
        }

    you_msgs = [m for m in user_msgs if m["user"] == user_id]
    them_msgs = [m for m in user_msgs if m["user"] != user_id]
    total = len(user_msgs)

    # Word counts
    you_words = [len(m.get("text", "").split()) for m in you_msgs] if you_msgs else [0]
    them_words = [len(m.get("text", "").split()) for m in them_msgs] if them_msgs else [0]

    # Sort by timestamp for sequential analysis
    sorted_msgs = sorted(user_msgs, key=lambda m: float(m["ts"]))

    # Initiations: first message after a gap > INITIATION_GAP_SECONDS
    you_initiated = 0
    them_initiated = 0
    if sorted_msgs:
        first = sorted_msgs[0]
        if first["user"] == user_id:
            you_initiated += 1
        else:
            them_initiated += 1
        for i in range(1, len(sorted_msgs)):
            gap = float(sorted_msgs[i]["ts"]) - float(sorted_msgs[i - 1]["ts"])
            if gap >= INITIATION_GAP_SECONDS:
                if sorted_msgs[i]["user"] == user_id:
                    you_initiated += 1
                else:
                    them_initiated += 1

    # Response times
    your_response_times = []
    their_response_times = []
    for i in range(1, len(sorted_msgs)):
        prev = sorted_msgs[i - 1]
        curr = sorted_msgs[i]
        delta = float(curr["ts"]) - float(prev["ts"])
        if delta >= INITIATION_GAP_SECONDS:
            continue
        if prev["user"] != user_id and curr["user"] == user_id:
            your_response_times.append(delta)
        elif prev["user"] == user_id and curr["user"] != user_id:
            their_response_times.append(delta)

    your_avg_resp = int(sum(your_response_times) / len(your_response_times)) if your_response_times else 0
    their_avg_resp = int(sum(their_response_times) / len(their_response_times)) if their_response_times else 0

    # Time breakdowns
    weekday: Counter[str] = Counter()
    hourly: Counter[int] = Counter()
    timestamps = []
    for m in sorted_msgs:
        dt = datetime.fromtimestamp(float(m["ts"]), tz=timezone.utc).astimezone()
        weekday[dt.strftime("%A")] += 1
        hourly[dt.hour] += 1
        timestamps.append(float(m["ts"]))

    span_days = 0
    if len(timestamps) >= 2:
        first_dt = datetime.fromtimestamp(timestamps[0], tz=timezone.utc).astimezone()
        last_dt = datetime.fromtimestamp(timestamps[-1], tz=timezone.utc).astimezone()
        span_days = (last_dt - first_dt).days + 1

    return {
        "total_messages": total,
        "you_count": len(you_msgs),
        "them_count": len(them_msgs),
        "you_pct": round(len(you_msgs) / total * 100, 1) if total else 0.0,
        "them_pct": round(len(them_msgs) / total * 100, 1) if total else 0.0,
        "your_avg_words": round(sum(you_words) / len(you_words), 1) if you_words else 0.0,
        "their_avg_words": round(sum(them_words) / len(them_words), 1) if them_words else 0.0,
        "you_initiated": you_initiated,
        "them_initiated": them_initiated,
        "your_avg_response_seconds": your_avg_resp,
        "their_avg_response_seconds": their_avg_resp,
        "weekday_breakdown": dict(weekday),
        "hourly_breakdown": dict(sorted(hourly.items())),
        "span_days": span_days,
        "first_ts": timestamps[0] if timestamps else 0,
        "last_ts": timestamps[-1] if timestamps else 0,
    }


def format_message_report(stats: dict, channel_label: str) -> str:
    if stats["total_messages"] == 0:
        return f"\nMessage Analytics\n=================\nChannel: {channel_label}\n\nNo messages found.\n"

    lines = []
    lines.append("")
    lines.append("Message Analytics")
    lines.append("=" * 50)
    lines.append(f"Channel:  {channel_label}")

    if stats["first_ts"] and stats["last_ts"]:
        first_date = datetime.fromtimestamp(stats["first_ts"], tz=timezone.utc).astimezone()
        last_date = datetime.fromtimestamp(stats["last_ts"], tz=timezone.utc).astimezone()
        lines.append(f"Period:   {first_date.strftime('%Y-%m-%d')} -> {last_date.strftime('%Y-%m-%d')} ({stats['span_days']} days)")
    lines.append("")

    # Volume
    lines.append("Volume")
    lines.append("-" * 50)
    lines.append(f"  Total messages:   {stats['total_messages']:,}")
    lines.append(f"  You:              {stats['you_count']:,} ({stats['you_pct']:.0f}%)")
    lines.append(f"  Them:             {stats['them_count']:,} ({stats['them_pct']:.0f}%)")
    if stats["span_days"] > 0:
        per_week = stats["total_messages"] / max(stats["span_days"] / 7, 1)
        lines.append(f"  Per week:         {per_week:.1f} messages")

    # Who initiates
    total_init = stats["you_initiated"] + stats["them_initiated"]
    if total_init > 0:
        lines.append("")
        lines.append("Who Initiates")
        lines.append("-" * 50)
        you_init_pct = stats["you_initiated"] / total_init * 100
        them_init_pct = stats["them_initiated"] / total_init * 100
        lines.append(f"  You:              {stats['you_initiated']} ({you_init_pct:.0f}%)")
        lines.append(f"  Them:             {stats['them_initiated']} ({them_init_pct:.0f}%)")
        lines.append(f"  (gap threshold: 4 hours)")

    # Response time
    if stats["your_avg_response_seconds"] > 0 or stats["their_avg_response_seconds"] > 0:
        lines.append("")
        lines.append("Response Time")
        lines.append("-" * 50)
        lines.append(f"  Your avg reply:   {format_duration(stats['your_avg_response_seconds'])}")
        lines.append(f"  Their avg reply:  {format_duration(stats['their_avg_response_seconds'])}")

    # Message style
    lines.append("")
    lines.append("Message Style")
    lines.append("-" * 50)
    lines.append(f"  Your avg length:  {stats['your_avg_words']:.1f} words")
    lines.append(f"  Their avg length: {stats['their_avg_words']:.1f} words")

    # Hourly breakdown - top 5 hours
    hourly = stats.get("hourly_breakdown", {})
    if hourly:
        lines.append("")
        lines.append("Most Active Hours")
        lines.append("-" * 50)
        top_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)[:5]
        top_hours.sort(key=lambda x: x[0])
        for hour, count in top_hours:
            lines.append(f"  {hour:02d}:00         {count:>6,}")

    # Day of week
    weekday = stats.get("weekday_breakdown", {})
    if weekday:
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        sorted_days = sorted(weekday.items(), key=lambda x: day_order.index(x[0]) if x[0] in day_order else 7)
        lines.append("")
        lines.append("By Day of Week")
        lines.append("-" * 50)
        for day, count in sorted_days:
            lines.append(f"  {day:<12} {count:>8,}")

    lines.append("")
    return "\n".join(lines)
