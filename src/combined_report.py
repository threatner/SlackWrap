from datetime import datetime, timezone
from src.report import format_duration, DAY_ORDER, format_pct_change, format_month_label


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

    # --- Trends ---
    if has_messages and m_stats.get("trend_last_30d_count") is not None:
        lines.append("Trends")
        lines.append("-" * 55)
        pct_30d_str = format_pct_change(m_stats.get("trend_30d_pct_change"))
        lines.append(f"  Last 30 days:     {m_stats['trend_last_30d_count']:,} messages ({pct_30d_str} vs previous 30d)")
        pct_yoy_str = format_pct_change(m_stats.get("trend_yoy_pct_change"))
        current_month_display = format_month_label(m_stats.get("trend_current_month", ""))
        yoy_label = m_stats.get("trend_yoy_month", "")
        yoy_display = format_month_label(yoy_label) if yoy_label else "prior year"
        lines.append(f"  {current_month_display + ':':<16} {m_stats['trend_current_month_count']:,} messages ({pct_yoy_str} daily avg vs {yoy_display})")
        lines.append("")

    # --- Thread Activity ---
    if has_messages and m_stats.get("top_level_messages") is not None:
        top_lvl = m_stats.get("top_level_messages", 0)
        thr_msgs = m_stats.get("thread_messages", 0)
        thr_pct = m_stats.get("thread_pct", 0.0)
        you_started = m_stats.get("threads_started_by_you", 0)
        them_started = m_stats.get("threads_started_by_them", 0)
        if top_lvl > 0 or thr_msgs > 0:
            top_pct = round(top_lvl / m_stats["total_messages"] * 100) if m_stats["total_messages"] else 0
            lines.append("Thread Activity")
            lines.append("-" * 55)
            lines.append(f"  Total messages:   {m_stats['total_messages']:,}")
            lines.append(f"  Top-level:        {top_lvl:,} ({top_pct}%)")
            lines.append(f"  In threads:       {thr_msgs:,} ({round(thr_pct)}%)")
            if you_started > 0 or them_started > 0:
                lines.append(f"  Threads started:  {your_name}: {you_started} / {their_name}: {them_started}")
            lines.append("")

    # --- Who Starts Huddles ---
    if has_huddles:
        h_total = h_stats["total_huddles"]
        h_you_pct = (h_stats["started_by_you"] / h_total * 100) if h_total else 0
        h_them_pct = (h_stats["started_by_them"] / h_total * 100) if h_total else 0
        lines.append("Who Starts Huddles")
        lines.append("-" * 55)
        lines.append(f"  {your_name + ':':<16} {h_stats['started_by_you']} ({h_you_pct:.0f}%)")
        lines.append(f"  {their_name + ':':<16} {h_stats['started_by_them']} ({h_them_pct:.0f}%)")
        lines.append("")

    # --- Response Time ---
    if has_messages and (m_stats["your_avg_response_seconds"] > 0 or m_stats["their_avg_response_seconds"] > 0):
        lines.append("Response Time (Messages)")
        lines.append("-" * 55)
        lines.append(f"  {your_name + ':':<16} {format_duration(m_stats['your_median_response_seconds'])} median, {format_duration(m_stats['your_avg_response_seconds'])} avg")
        lines.append(f"  {their_name + ':':<16} {format_duration(m_stats['their_median_response_seconds'])} median, {format_duration(m_stats['their_avg_response_seconds'])} avg")
        lines.append("")

    # --- Response Time by Hour ---
    if has_messages:
        resp_by_hour = m_stats.get("response_time_by_hour", {})
        if resp_by_hour:
            lines.append("Response Time by Hour")
            lines.append("-" * 55)
            fastest_hour = min(resp_by_hour, key=resp_by_hour.get)
            slowest_hour = max(resp_by_hour, key=resp_by_hour.get)
            lines.append(f"  Fastest:          {fastest_hour:02d}:00 ({format_duration(resp_by_hour[fastest_hour])} median)")
            lines.append(f"  Slowest:          {slowest_hour:02d}:00 ({format_duration(resp_by_hour[slowest_hour])} median)")
            lines.append("")

    # --- Links & Files ---
    if has_messages:
        your_links = m_stats.get("your_links_shared", 0)
        their_links = m_stats.get("their_links_shared", 0)
        your_files = m_stats.get("your_files_shared", 0)
        their_files = m_stats.get("their_files_shared", 0)
        if your_links > 0 or their_links > 0 or your_files > 0 or their_files > 0:
            lines.append("Links & Files")
            lines.append("-" * 55)
            lines.append(f"  {your_name + ':':<16} {your_links} links, {your_files} files")
            lines.append(f"  {their_name + ':':<16} {their_links} links, {their_files} files")
            lines.append("")

    # --- Message Style ---
    if has_messages:
        lines.append("Message Style")
        lines.append("-" * 55)
        lines.append(f"  {your_name + ':':<16} {m_stats['your_avg_words']:.1f} words avg")
        lines.append(f"  {their_name + ":":<16} {m_stats['their_avg_words']:.1f} words avg")
        lines.append("")

    # --- Conversation Streaks ---
    if has_messages and m_stats.get("longest_streak_days", 0) > 0:
        lines.append("Conversation Streaks")
        lines.append("-" * 55)
        streak_start_dt = datetime.fromtimestamp(m_stats["longest_streak_start"], tz=timezone.utc).astimezone()
        streak_end_dt = datetime.fromtimestamp(m_stats["longest_streak_end"], tz=timezone.utc).astimezone()
        streak_range = f"{streak_start_dt.strftime('%b %-d')} - {streak_end_dt.strftime('%b %-d')}"
        lines.append(f"  Longest streak:   {m_stats['longest_streak_days']} days ({streak_range})")
        lines.append(f"  Current streak:   {m_stats['current_streak_days']} days")
        if m_stats.get("longest_gap_seconds", 0) > 0:
            gap_days = m_stats["longest_gap_seconds"] // 86400
            gap_start_dt = datetime.fromtimestamp(m_stats["longest_gap_start"], tz=timezone.utc).astimezone()
            gap_end_dt = datetime.fromtimestamp(m_stats["longest_gap_end"], tz=timezone.utc).astimezone()
            gap_range = f"{gap_start_dt.strftime('%b %-d')} - {gap_end_dt.strftime('%b %-d')}"
            lines.append(f"  Longest silence:  {gap_days} days ({gap_range})")
        lines.append("")

    # --- First & Last Message ---
    if has_messages and m_stats.get("first_message") and m_stats.get("last_message"):
        lines.append("First & Last")
        lines.append("-" * 55)
        fm = m_stats["first_message"]
        lm = m_stats["last_message"]
        fm_dt = datetime.fromtimestamp(fm["ts"], tz=timezone.utc).astimezone()
        lm_dt = datetime.fromtimestamp(lm["ts"], tz=timezone.utc).astimezone()
        lines.append(f"  First message:    {fm_dt.strftime('%Y-%m-%d')}")
        lines.append(f"                    \"{fm['text']}\"")
        lines.append(f"  Last message:     {lm_dt.strftime('%Y-%m-%d')}")
        lines.append(f"                    \"{lm['text']}\"")
        lines.append("")

    # --- Emojis in Messages ---
    has_text_emoji = has_messages and (
        m_stats.get("your_text_emoji_total", 0) > 0 or m_stats.get("their_text_emoji_total", 0) > 0
    )
    if has_text_emoji:
        lines.append("Emojis Used in Messages")
        lines.append("-" * 55)
        lines.append(f"  {your_name + ':':<16} {m_stats['your_text_emoji_total']:,} emojis")
        if m_stats.get("your_top_text_emojis"):
            top_str = ", ".join(f":{name}: ({count})" for name, count in m_stats["your_top_text_emojis"])
            lines.append(f"    Top:            {top_str}")
        lines.append(f"  {their_name + ':':<16} {m_stats['their_text_emoji_total']:,} emojis")
        if m_stats.get("their_top_text_emojis"):
            top_str = ", ".join(f":{name}: ({count})" for name, count in m_stats["their_top_text_emojis"])
            lines.append(f"    Top:            {top_str}")
        lines.append("")

    # --- Reactions on Messages ---
    has_reactions = has_messages and (
        m_stats.get("your_reactions_given", 0) > 0 or m_stats.get("their_reactions_given", 0) > 0
    )
    if has_reactions:
        lines.append("Reactions on Messages")
        lines.append("-" * 55)
        lines.append(f"  {your_name + ':':<16} {m_stats['your_reactions_given']:,} given")
        lines.append(f"  {their_name + ':':<16} {m_stats['their_reactions_given']:,} given")
        if m_stats.get("top_reactions"):
            top_str = ", ".join(f":{name}: ({count})" for name, count in m_stats["top_reactions"])
            lines.append(f"  Top:              {top_str}")
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
    if has_huddles and has_messages and h_stats["total_huddles"] > 0:
        ratio = m_stats["total_messages"] / h_stats["total_huddles"]
        lines.append(f"  Per huddle:       ~{ratio:.0f} messages exchanged")
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
