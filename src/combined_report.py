from datetime import datetime, timezone
from src.report import format_duration

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def format_combined_report(h_stats: dict, m_stats: dict, channel_label: str, your_name: str = "You", their_name: str = "Them") -> str:
    has_huddles = h_stats["total_huddles"] > 0
    has_messages = m_stats["total_messages"] > 0

    if not has_huddles and not has_messages:
        return f"\nSlack Analytics\n===============\nChannel: {channel_label}\n\nNo data found.\n"

    lines = []
    lines.append("")
    lines.append("Slack Analytics")
    lines.append("=" * 55)
    lines.append(f"Channel:  {channel_label}")

    # Period — use the widest range from either dataset
    all_ts = []
    if has_huddles:
        all_ts.extend(h["room"]["date_start"] for h in h_stats["huddles"])
    if has_messages and m_stats["first_ts"]:
        all_ts.extend([m_stats["first_ts"], m_stats["last_ts"]])
    if all_ts:
        first_date = datetime.fromtimestamp(min(all_ts), tz=timezone.utc).astimezone()
        last_date = datetime.fromtimestamp(max(all_ts), tz=timezone.utc).astimezone()
        span_days = (last_date - first_date).days + 1
        lines.append(f"Period:   {first_date.strftime('%Y-%m-%d')} -> {last_date.strftime('%Y-%m-%d')} ({span_days} days)")
    else:
        span_days = 1
    lines.append("")

    # --- Huddle Time ---
    if has_huddles:
        total_hrs = h_stats["total_seconds"] / 3600
        avg_hrs = h_stats["avg_seconds"] / 3600
        lines.append("Huddle Time")
        lines.append("-" * 55)
        lines.append(f"  Total time:       {format_duration(h_stats['total_seconds'])} ({total_hrs:.1f} hours)")
        lines.append(f"  Total huddles:    {h_stats['total_huddles']}")
        lines.append(f"  Average:          {format_duration(h_stats['avg_seconds'])} per huddle ({avg_hrs:.1f} hrs)")
        lines.append(f"  Median:           {format_duration(h_stats['median_seconds'])} per huddle")
        lines.append(f"  Longest:          {format_duration(h_stats['longest_seconds'])}")
        lines.append(f"  Shortest:         {format_duration(h_stats['shortest_seconds'])}")
        lines.append("")

    # --- Messages ---
    if has_messages:
        lines.append("Messages")
        lines.append("-" * 55)
        lines.append(f"  Total messages:   {m_stats['total_messages']:,}")
        lines.append(f"  {your_name + ':':<16} {m_stats['you_count']:,} ({m_stats['you_pct']:.0f}%)")
        lines.append(f"  {their_name + ":":<16} {m_stats['them_count']:,} ({m_stats['them_pct']:.0f}%)")
        if m_stats["span_days"] > 0:
            per_week = m_stats["total_messages"] / max(m_stats["span_days"] / 7, 1)
            lines.append(f"  Per week:         {per_week:.1f} messages")
        lines.append("")

    # --- Who Initiates (combined) ---
    lines.append("Who Initiates")
    lines.append("-" * 55)
    if has_huddles:
        h_total = h_stats["total_huddles"]
        h_you_pct = (h_stats["started_by_you"] / h_total * 100) if h_total else 0
        h_them_pct = (h_stats["started_by_them"] / h_total * 100) if h_total else 0
        lines.append(f"  Huddles    {your_name}: {h_stats['started_by_you']} ({h_you_pct:.0f}%)     {their_name}: {h_stats['started_by_them']} ({h_them_pct:.0f}%)")
    if has_messages:
        m_init_total = m_stats["you_initiated"] + m_stats["them_initiated"]
        if m_init_total > 0:
            m_you_pct = m_stats["you_initiated"] / m_init_total * 100
            m_them_pct = m_stats["them_initiated"] / m_init_total * 100
            lines.append(f"  Messages   {your_name}: {m_stats['you_initiated']} ({m_you_pct:.0f}%)     {their_name}: {m_stats['them_initiated']} ({m_them_pct:.0f}%)")
    lines.append("")

    # --- Response Time ---
    if has_messages and (m_stats["your_avg_response_seconds"] > 0 or m_stats["their_avg_response_seconds"] > 0):
        lines.append("Response Time (Messages)")
        lines.append("-" * 55)
        lines.append(f"  {your_name + ':':<16} {format_duration(m_stats['your_median_response_seconds'])} median, {format_duration(m_stats['your_avg_response_seconds'])} avg")
        lines.append(f"  {their_name + ':':<16} {format_duration(m_stats['their_median_response_seconds'])} median, {format_duration(m_stats['their_avg_response_seconds'])} avg")
        lines.append("")

    # --- Message Style ---
    if has_messages:
        lines.append("Message Style")
        lines.append("-" * 55)
        lines.append(f"  {your_name + ':':<16} {m_stats['your_avg_words']:.1f} words avg")
        lines.append(f"  {their_name + ":":<16} {m_stats['their_avg_words']:.1f} words avg")
        lines.append("")

    # --- Frequency (combined) ---
    weeks = max(span_days / 7, 1)
    lines.append("Frequency")
    lines.append("-" * 55)
    if has_huddles:
        lines.append(f"  Huddles/week:     {h_stats['total_huddles'] / weeks:.1f} ({format_duration(int(h_stats['total_seconds'] / weeks))})")
    if has_messages and m_stats["span_days"] > 0:
        m_weeks = max(m_stats["span_days"] / 7, 1)
        lines.append(f"  Messages/week:    {m_stats['total_messages'] / m_weeks:.1f}")
    lines.append("")

    # --- By Day of Week (combined table) ---
    h_weekday = h_stats.get("weekday_breakdown", {}) if has_huddles else {}
    m_weekday = m_stats.get("weekday_breakdown", {}) if has_messages else {}
    if h_weekday or m_weekday:
        lines.append("By Day of Week")
        lines.append("-" * 55)
        if has_huddles and has_messages:
            lines.append(f"  {'':12} {'Huddles':>8}  {'Messages':>8}")
            for day in DAY_ORDER:
                h_count = h_weekday.get(day, 0)
                m_count = m_weekday.get(day, 0)
                if h_count > 0 or m_count > 0:
                    lines.append(f"  {day:<12} {h_count:>8}  {m_count:>8,}")
        elif has_huddles:
            for day in DAY_ORDER:
                count = h_weekday.get(day, 0)
                if count > 0:
                    lines.append(f"  {day:<12} {count:>5}")
        else:
            for day in DAY_ORDER:
                count = m_weekday.get(day, 0)
                if count > 0:
                    lines.append(f"  {day:<12} {count:>8,}")
        lines.append("")

    # --- Most Active Hours (messages) ---
    hourly = m_stats.get("hourly_breakdown", {}) if has_messages else {}
    if hourly:
        lines.append("Most Active Hours (Messages)")
        lines.append("-" * 55)
        top_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)[:5]
        top_hours.sort(key=lambda x: x[0])
        for hour, count in top_hours:
            lines.append(f"  {hour:02d}:00         {count:>6,}")
        lines.append("")

    return "\n".join(lines)
