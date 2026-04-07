import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from src.report import format_duration, format_pct_change, format_month_label, median, DAY_ORDER

SYSTEM_SUBTYPES = {
    "huddle_thread", "channel_join", "channel_leave", "channel_topic",
    "channel_purpose", "channel_name", "bot_message", "bot_add",
    "bot_remove", "file_comment", "file_mention",
    "pinned_item", "unpinned_item", "group_join", "group_leave",
    "group_topic", "group_purpose", "group_name", "channel_archive",
    "channel_unarchive", "ekm_access_denied", "reminder_add",
    "sh_room_created", "tombstone",
}


# Regex to strip Slack markup before word counting
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")  # triple-backtick code blocks
_INLINE_CODE_RE = re.compile(r"`[^`]+`")  # inline code
_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]*)?>")  # <@U12345> or <@U12345|name>
_LINK_RE = re.compile(r"<https?://[^>]+>")  # <https://...|label>
_EMOJI_RE = re.compile(r":[a-zA-Z0-9_+-]+:")  # :thumbsup:
_EMOJI_EXTRACT_RE = re.compile(r":([a-zA-Z0-9_+-]+):")  # capture emoji names from text


def _extract_text_emojis(text: str) -> list[str]:
    # Strip code blocks first so we don't count emoji in code
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    return _EMOJI_EXTRACT_RE.findall(text)


def _clean_text_for_word_count(text: str) -> str:
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _MENTION_RE.sub("", text)
    text = _LINK_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    return text.strip()


def _clean_text_for_word_count_prestripped(text: str) -> str:
    """Like _clean_text_for_word_count but skips code-block stripping (already done)."""
    text = _MENTION_RE.sub("", text)
    text = _LINK_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    return text.strip()


def _filter_user_messages(messages: list[dict]) -> list[dict]:
    return [
        m for m in messages
        if m.get("subtype") not in SYSTEM_SUBTYPES
        and m.get("user") is not None
        and m.get("user") != "USLACKBOT"
    ]


def _build_turns(sorted_msgs: list[dict]) -> list[dict]:
    """Collapse consecutive same-user messages into turns.

    Each turn has: user, start_ts (first msg), end_ts (last msg), count.
    """
    if not sorted_msgs:
        return []
    turns = []
    current = {
        "user": sorted_msgs[0]["user"],
        "start_ts": float(sorted_msgs[0]["ts"]),
        "end_ts": float(sorted_msgs[0]["ts"]),
        "count": 1,
    }
    for msg in sorted_msgs[1:]:
        if msg["user"] == current["user"]:
            current["end_ts"] = float(msg["ts"])
            current["count"] += 1
        else:
            turns.append(current)
            current = {
                "user": msg["user"],
                "start_ts": float(msg["ts"]),
                "end_ts": float(msg["ts"]),
                "count": 1,
            }
    turns.append(current)
    return turns


def compute_message_stats(messages: list[dict], user_id: str, target_user_id: str | None = None) -> dict:
    user_msgs = _filter_user_messages(messages)
    if target_user_id:
        user_msgs = [m for m in user_msgs if m["user"] in (user_id, target_user_id)]

    if not user_msgs:
        return {
            "total_messages": 0,
            "you_count": 0, "them_count": 0,
            "you_pct": 0.0, "them_pct": 0.0,
            "your_avg_words": 0.0, "their_avg_words": 0.0,
            "your_avg_response_seconds": 0, "their_avg_response_seconds": 0,
            "your_median_response_seconds": 0, "their_median_response_seconds": 0,
            "weekday_breakdown": {}, "hourly_breakdown": {}, "monthly_breakdown": {},
            "span_days": 0, "first_ts": 0, "last_ts": 0,
            "longest_streak_days": 0, "longest_streak_start": 0, "longest_streak_end": 0,
            "current_streak_days": 0,
            "longest_gap_seconds": 0, "longest_gap_start": 0, "longest_gap_end": 0,
            "first_message": None, "last_message": None,
            "your_reactions_given": 0, "their_reactions_given": 0,
            "top_reactions": [], "your_top_reactions": [], "their_top_reactions": [],
            "your_text_emoji_total": 0, "their_text_emoji_total": 0,
            "your_top_text_emojis": [], "their_top_text_emojis": [],
            "trend_last_30d_count": 0,
            "trend_prev_30d_count": 0,
            "trend_30d_pct_change": None,
            "trend_current_month": "",
            "trend_current_month_count": 0,
            "trend_yoy_month": "",
            "trend_yoy_count": None,
            "trend_yoy_pct_change": None,
            "top_level_messages": 0,
            "thread_messages": 0,
            "thread_pct": 0.0,
            "threads_started_by_you": 0,
            "threads_started_by_them": 0,
            "response_time_by_hour": {},
            "your_links_shared": 0,
            "their_links_shared": 0,
            "your_files_shared": 0,
            "their_files_shared": 0,
        }

    you_msgs = [m for m in user_msgs if m["user"] == user_id]
    them_msgs = [m for m in user_msgs if m["user"] != user_id]
    total = len(user_msgs)

    # Strip code blocks once per message; reuse for word counts and emoji extraction
    _cleaned_texts: dict[str, str] = {}
    for m in user_msgs:
        text = m.get("text", "")
        text = _CODE_BLOCK_RE.sub("", text)
        text = _INLINE_CODE_RE.sub("", text)
        _cleaned_texts[m["ts"]] = text

    # Word counts — strip code blocks (pre-stripped), mentions, links, emoji
    you_words = [len(_clean_text_for_word_count_prestripped(_cleaned_texts[m["ts"]]).split()) for m in you_msgs] if you_msgs else [0]
    them_words = [len(_clean_text_for_word_count_prestripped(_cleaned_texts[m["ts"]]).split()) for m in them_msgs] if them_msgs else [0]
    # Filter out zero-word messages (file uploads with no text) from avg
    you_words_nonzero = [w for w in you_words if w > 0] or [0]
    them_words_nonzero = [w for w in them_words if w > 0] or [0]

    # Sort by timestamp for sequential analysis
    sorted_msgs = sorted(user_msgs, key=lambda m: float(m["ts"]))

    # Build conversation turns (collapse consecutive same-user messages)
    turns = _build_turns(sorted_msgs)

    # Response times — measured turn-to-turn
    # From the START of turn A to the START of turn B (first msg in each turn)
    your_response_times = []
    their_response_times = []
    for i in range(1, len(turns)):
        prev_turn = turns[i - 1]
        curr_turn = turns[i]
        delta = int(curr_turn["start_ts"] - prev_turn["start_ts"])
        # Skip gaps > 4 hours (overnight, weekends) for response time
        if delta >= 4 * 3600:
            continue
        if prev_turn["user"] != user_id and curr_turn["user"] == user_id:
            your_response_times.append(delta)
        elif prev_turn["user"] == user_id and curr_turn["user"] != user_id:
            their_response_times.append(delta)

    your_avg_resp = int(sum(your_response_times) / len(your_response_times)) if your_response_times else 0
    their_avg_resp = int(sum(their_response_times) / len(their_response_times)) if their_response_times else 0
    your_median_resp = median(your_response_times)
    their_median_resp = median(their_response_times)

    # Time breakdowns + active dates (single pass)
    weekday: Counter[str] = Counter()
    hourly: Counter[int] = Counter()
    monthly: Counter[str] = Counter()
    timestamps = []
    active_dates_set = set()
    for m in sorted_msgs:
        ts_float = float(m["ts"])
        dt = datetime.fromtimestamp(ts_float, tz=timezone.utc).astimezone()
        weekday[dt.strftime("%A")] += 1
        hourly[dt.hour] += 1
        monthly[dt.strftime("%Y-%m")] += 1
        timestamps.append(ts_float)
        active_dates_set.add(dt.date())

    active_dates = sorted(active_dates_set)

    span_days = 0
    if len(timestamps) >= 2:
        first_dt = datetime.fromtimestamp(timestamps[0], tz=timezone.utc).astimezone()
        last_dt = datetime.fromtimestamp(timestamps[-1], tz=timezone.utc).astimezone()
        span_days = (last_dt - first_dt).days + 1

    # --- Conversation Streaks ---

    longest_streak_days = 0
    longest_streak_start_ts = 0.0
    longest_streak_end_ts = 0.0
    current_streak_days = 0

    if active_dates:
        # Find longest streak
        streak_start = active_dates[0]
        streak_len = 1
        best_start = active_dates[0]
        best_len = 1

        for i in range(1, len(active_dates)):
            if active_dates[i] == active_dates[i - 1] + timedelta(days=1):
                streak_len += 1
            else:
                if streak_len > best_len:
                    best_len = streak_len
                    best_start = streak_start
                streak_start = active_dates[i]
                streak_len = 1
        # Check last streak
        if streak_len > best_len:
            best_len = streak_len
            best_start = streak_start

        best_end = best_start + timedelta(days=best_len - 1)
        longest_streak_days = best_len
        longest_streak_start_ts = float(
            datetime(best_start.year, best_start.month, best_start.day, tzinfo=timezone.utc).timestamp()
        )
        longest_streak_end_ts = float(
            datetime(best_end.year, best_end.month, best_end.day, tzinfo=timezone.utc).timestamp()
        )

        # Current streak (from the last active date going backwards)
        last_active = active_dates[-1]
        cur_len = 1
        for i in range(len(active_dates) - 2, -1, -1):
            if active_dates[i] == active_dates[i + 1] - timedelta(days=1):
                cur_len += 1
            else:
                break
        current_streak_days = cur_len

    # --- Dead Zones (longest gap between consecutive messages) ---
    longest_gap_seconds = 0
    longest_gap_start_ts = 0.0
    longest_gap_end_ts = 0.0

    if len(timestamps) >= 2:
        for i in range(1, len(timestamps)):
            gap = int(timestamps[i] - timestamps[i - 1])
            if gap > longest_gap_seconds:
                longest_gap_seconds = gap
                longest_gap_start_ts = timestamps[i - 1]
                longest_gap_end_ts = timestamps[i]

    # --- First & Last Message ---
    def _trim_msg(m: dict) -> dict:
        return {
            "user": m.get("user", ""),
            "text": (m.get("text") or "")[:100],
            "ts": float(m["ts"]),
        }

    first_message = _trim_msg(sorted_msgs[0])
    last_message = _trim_msg(sorted_msgs[-1])

    # --- Emoji / Reaction Analytics ---
    # Operate on ALL messages passed in (before subtype filtering)
    your_reactions_given = 0
    their_reactions_given = 0
    all_reaction_counter: Counter[str] = Counter()
    your_reaction_counter: Counter[str] = Counter()
    their_reaction_counter: Counter[str] = Counter()

    for m in messages:
        for reaction in m.get("reactions", []):
            name = reaction.get("name", "")
            users_who_reacted = reaction.get("users", [])
            for uid in users_who_reacted:
                if uid == user_id:
                    your_reactions_given += 1
                    your_reaction_counter[name] += 1
                    all_reaction_counter[name] += 1
                elif target_user_id and uid == target_user_id:
                    their_reactions_given += 1
                    their_reaction_counter[name] += 1
                    all_reaction_counter[name] += 1
                elif not target_user_id:
                    # No target filter — count all non-you reactions as "theirs"
                    their_reactions_given += 1
                    their_reaction_counter[name] += 1
                    all_reaction_counter[name] += 1

    top_reactions = all_reaction_counter.most_common(5)
    your_top_reactions = your_reaction_counter.most_common(3)
    their_top_reactions = their_reaction_counter.most_common(3)

    # --- Emojis Used in Messages (text) ---
    your_text_emoji_counter: Counter[str] = Counter()
    their_text_emoji_counter: Counter[str] = Counter()
    for m in user_msgs:
        cleaned = _cleaned_texts[m["ts"]]
        emojis = _EMOJI_EXTRACT_RE.findall(cleaned)
        if m["user"] == user_id:
            your_text_emoji_counter.update(emojis)
        else:
            their_text_emoji_counter.update(emojis)

    your_text_emoji_total = sum(your_text_emoji_counter.values())
    their_text_emoji_total = sum(their_text_emoji_counter.values())
    your_top_text_emojis = your_text_emoji_counter.most_common(5)
    their_top_text_emojis = their_text_emoji_counter.most_common(5)

    # --- Response Time by Hour ---
    response_by_hour: dict[int, list[int]] = {}
    for i in range(1, len(turns)):
        prev_turn = turns[i - 1]
        curr_turn = turns[i]
        delta = int(curr_turn["start_ts"] - prev_turn["start_ts"])
        if delta >= 4 * 3600:
            continue
        if prev_turn["user"] != curr_turn["user"]:
            hour = datetime.fromtimestamp(curr_turn["start_ts"], tz=timezone.utc).astimezone().hour
            if hour not in response_by_hour:
                response_by_hour[hour] = []
            response_by_hour[hour].append(delta)

    response_time_by_hour: dict[int, int] = {}
    for hour, times in sorted(response_by_hour.items()):
        if len(times) >= 3:
            response_time_by_hour[hour] = median(times)

    # --- Links & Files ---
    your_links = sum(len(_LINK_RE.findall(m.get("text", ""))) for m in you_msgs)
    their_links = sum(len(_LINK_RE.findall(m.get("text", ""))) for m in them_msgs)
    your_files = sum(m.get("files_count", 0) for m in you_msgs)
    their_files = sum(m.get("files_count", 0) for m in them_msgs)

    # --- Thread Breakdown ---
    top_level = [m for m in user_msgs if not m.get("thread_ts") or m.get("thread_ts") == m.get("ts")]
    thread_replies = [m for m in user_msgs if m.get("thread_ts") and m.get("thread_ts") != m.get("ts")]
    thread_pct = round(len(thread_replies) / total * 100, 1) if total else 0.0

    thread_parents_you = sum(1 for m in user_msgs if m.get("reply_count", 0) > 0 and m["user"] == user_id)
    thread_parents_them = sum(1 for m in user_msgs if m.get("reply_count", 0) > 0 and m["user"] != user_id)

    # --- Trend Analysis ---
    now = date.today()
    now_ts = datetime.now(tz=timezone.utc).timestamp()
    cutoff_30d = now_ts - 30 * 86400
    cutoff_60d = now_ts - 60 * 86400
    trend_last_30d = sum(1 for t in timestamps if t >= cutoff_30d)
    trend_prev_30d = sum(1 for t in timestamps if cutoff_60d <= t < cutoff_30d)
    trend_30d_pct = round((trend_last_30d - trend_prev_30d) / trend_prev_30d * 100, 1) if trend_prev_30d > 0 else None

    current_month = now.strftime("%Y-%m")
    yoy_month = f"{now.year - 1}-{now.strftime('%m')}"
    trend_current_month_count = monthly.get(current_month, 0)
    trend_yoy_count = monthly.get(yoy_month, None)
    # Normalize YoY to daily rate so partial current month vs full past month is fair
    days_into_month = now.day
    if trend_yoy_count and days_into_month > 0:
        import calendar
        _, yoy_total_days = calendar.monthrange(now.year - 1, now.month)
        current_daily_rate = trend_current_month_count / days_into_month
        yoy_daily_rate = trend_yoy_count / yoy_total_days
        trend_yoy_pct = round((current_daily_rate - yoy_daily_rate) / yoy_daily_rate * 100, 1) if yoy_daily_rate > 0 else None
    else:
        trend_yoy_pct = None

    return {
        "total_messages": total,
        "you_count": len(you_msgs),
        "them_count": len(them_msgs),
        "you_pct": round(len(you_msgs) / total * 100, 1) if total else 0.0,
        "them_pct": round(len(them_msgs) / total * 100, 1) if total else 0.0,
        "your_avg_words": round(sum(you_words_nonzero) / len(you_words_nonzero), 1),
        "their_avg_words": round(sum(them_words_nonzero) / len(them_words_nonzero), 1),
        "your_avg_response_seconds": your_avg_resp,
        "their_avg_response_seconds": their_avg_resp,
        "your_median_response_seconds": your_median_resp,
        "their_median_response_seconds": their_median_resp,
        "weekday_breakdown": dict(weekday),
        "hourly_breakdown": dict(sorted(hourly.items())),
        "monthly_breakdown": dict(sorted(monthly.items())),
        "span_days": span_days,
        "first_ts": timestamps[0] if timestamps else 0,
        "last_ts": timestamps[-1] if timestamps else 0,
        "longest_streak_days": longest_streak_days,
        "longest_streak_start": longest_streak_start_ts,
        "longest_streak_end": longest_streak_end_ts,
        "current_streak_days": current_streak_days,
        "longest_gap_seconds": longest_gap_seconds,
        "longest_gap_start": longest_gap_start_ts,
        "longest_gap_end": longest_gap_end_ts,
        "first_message": first_message,
        "last_message": last_message,
        "your_reactions_given": your_reactions_given,
        "their_reactions_given": their_reactions_given,
        "top_reactions": top_reactions,
        "your_top_reactions": your_top_reactions,
        "their_top_reactions": their_top_reactions,
        "your_text_emoji_total": your_text_emoji_total,
        "their_text_emoji_total": their_text_emoji_total,
        "your_top_text_emojis": your_top_text_emojis,
        "their_top_text_emojis": their_top_text_emojis,
        "trend_last_30d_count": trend_last_30d,
        "trend_prev_30d_count": trend_prev_30d,
        "trend_30d_pct_change": trend_30d_pct,
        "trend_current_month": current_month,
        "trend_current_month_count": trend_current_month_count,
        "trend_yoy_month": yoy_month,
        "trend_yoy_count": trend_yoy_count,
        "trend_yoy_pct_change": trend_yoy_pct,
        "top_level_messages": len(top_level),
        "thread_messages": len(thread_replies),
        "thread_pct": thread_pct,
        "threads_started_by_you": thread_parents_you,
        "threads_started_by_them": thread_parents_them,
        "response_time_by_hour": response_time_by_hour,
        "your_links_shared": your_links,
        "their_links_shared": their_links,
        "your_files_shared": your_files,
        "their_files_shared": their_files,
        "_user_id": user_id,
    }


def format_message_report(stats: dict, channel_label: str, your_name: str = "You", their_name: str = "Them") -> str:
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
    lines.append(f"  {your_name + ':':<16} {stats['you_count']:,} ({stats['you_pct']:.0f}%)")
    lines.append(f"  {their_name + ':':<16} {stats['them_count']:,} ({stats['them_pct']:.0f}%)")
    if stats["span_days"] > 0:
        per_week = stats["total_messages"] / max(stats["span_days"] / 7, 1)
        lines.append(f"  Per week:         {per_week:.1f} messages")

    # Trends
    if stats.get("trend_last_30d_count") is not None or stats.get("trend_prev_30d_count"):
        lines.append("")
        lines.append("Trends")
        lines.append("-" * 50)
        pct_30d_str = format_pct_change(stats.get("trend_30d_pct_change"))
        lines.append(f"  Last 30 days:     {stats['trend_last_30d_count']:,} messages ({pct_30d_str} vs previous 30d)")
        pct_yoy_str = format_pct_change(stats.get("trend_yoy_pct_change"))
        current_month_display = format_month_label(stats.get("trend_current_month", ""))
        yoy_label = stats.get("trend_yoy_month", "")
        yoy_display = format_month_label(yoy_label) if yoy_label else "prior year"
        lines.append(f"  {current_month_display + ':':<16} {stats['trend_current_month_count']:,} messages ({pct_yoy_str} daily avg vs {yoy_display})")

    # Thread Activity
    if stats.get("top_level_messages") is not None or stats.get("thread_messages"):
        lines.append("")
        lines.append("Thread Activity")
        lines.append("-" * 50)
        lines.append(f"  Total messages:   {stats['total_messages']:,}")
        top_pct = round((stats['top_level_messages'] / stats['total_messages'] * 100)) if stats['total_messages'] else 0
        thr_pct = round(stats.get('thread_pct', 0))
        lines.append(f"  Top-level:        {stats['top_level_messages']:,} ({top_pct}%)")
        lines.append(f"  In threads:       {stats['thread_messages']:,} ({thr_pct}%)")
        you_started = stats.get("threads_started_by_you", 0)
        them_started = stats.get("threads_started_by_them", 0)
        if you_started > 0 or them_started > 0:
            lines.append(f"  Threads started:  {your_name}: {you_started} / {their_name}: {them_started}")

    # Response time
    has_resp = stats["your_avg_response_seconds"] > 0 or stats["their_avg_response_seconds"] > 0
    if has_resp:
        lines.append("")
        lines.append("Response Time")
        lines.append("-" * 50)
        lines.append(f"  {your_name + ':':<16} {format_duration(stats['your_median_response_seconds'])} median, {format_duration(stats['your_avg_response_seconds'])} avg")
        lines.append(f"  {their_name + ':':<16} {format_duration(stats['their_median_response_seconds'])} median, {format_duration(stats['their_avg_response_seconds'])} avg")

    # Response Time by Hour
    resp_by_hour = stats.get("response_time_by_hour", {})
    if resp_by_hour:
        lines.append("")
        lines.append("Response Time by Hour")
        lines.append("-" * 50)
        fastest_hour = min(resp_by_hour, key=resp_by_hour.get)
        slowest_hour = max(resp_by_hour, key=resp_by_hour.get)
        lines.append(f"  Fastest:          {fastest_hour:02d}:00 ({format_duration(resp_by_hour[fastest_hour])} median)")
        lines.append(f"  Slowest:          {slowest_hour:02d}:00 ({format_duration(resp_by_hour[slowest_hour])} median)")

    # Links & Files
    your_links = stats.get("your_links_shared", 0)
    their_links = stats.get("their_links_shared", 0)
    your_files = stats.get("your_files_shared", 0)
    their_files = stats.get("their_files_shared", 0)
    if your_links > 0 or their_links > 0 or your_files > 0 or their_files > 0:
        lines.append("")
        lines.append("Links & Files")
        lines.append("-" * 50)
        lines.append(f"  {your_name + ':':<16} {your_links} links, {your_files} files")
        lines.append(f"  {their_name + ':':<16} {their_links} links, {their_files} files")

    # Message style
    lines.append("")
    lines.append("Message Style")
    lines.append("-" * 50)
    lines.append(f"  {your_name + ':':<16} {stats['your_avg_words']:.1f} words avg")
    lines.append(f"  {their_name + ':':<16} {stats['their_avg_words']:.1f} words avg")

    # Conversation Streaks
    if stats.get("longest_streak_days", 0) > 0:
        lines.append("")
        lines.append("Conversation Streaks")
        lines.append("-" * 50)
        streak_start_dt = datetime.fromtimestamp(stats["longest_streak_start"], tz=timezone.utc).astimezone()
        streak_end_dt = datetime.fromtimestamp(stats["longest_streak_end"], tz=timezone.utc).astimezone()
        streak_range = f"{streak_start_dt.strftime('%b %-d')} - {streak_end_dt.strftime('%b %-d')}"
        lines.append(f"  Longest streak:   {stats['longest_streak_days']} days ({streak_range})")
        lines.append(f"  Current streak:   {stats['current_streak_days']} days")
        if stats.get("longest_gap_seconds", 0) > 0:
            gap_days = stats["longest_gap_seconds"] // 86400
            gap_start_dt = datetime.fromtimestamp(stats["longest_gap_start"], tz=timezone.utc).astimezone()
            gap_end_dt = datetime.fromtimestamp(stats["longest_gap_end"], tz=timezone.utc).astimezone()
            gap_range = f"{gap_start_dt.strftime('%b %-d')} - {gap_end_dt.strftime('%b %-d')}"
            lines.append(f"  Longest silence:  {gap_days} days ({gap_range})")

    # First & Last Message
    if stats.get("first_message") and stats.get("last_message"):
        lines.append("")
        lines.append("First & Last")
        lines.append("-" * 50)
        fm = stats["first_message"]
        lm = stats["last_message"]
        fm_name = your_name if fm["user"] == stats.get("_user_id") else their_name
        lm_name = your_name if lm["user"] == stats.get("_user_id") else their_name
        fm_dt = datetime.fromtimestamp(fm["ts"], tz=timezone.utc).astimezone()
        lm_dt = datetime.fromtimestamp(lm["ts"], tz=timezone.utc).astimezone()
        lines.append(f"  First message:    {fm_dt.strftime('%Y-%m-%d')} by {fm_name}")
        lines.append(f"                    \"{fm['text']}\"")
        lines.append(f"  Last message:     {lm_dt.strftime('%Y-%m-%d')} by {lm_name}")
        lines.append(f"                    \"{lm['text']}\"")

    # Emojis in Messages
    has_text_emoji = stats.get("your_text_emoji_total", 0) > 0 or stats.get("their_text_emoji_total", 0) > 0
    if has_text_emoji:
        lines.append("")
        lines.append("Emojis Used in Messages")
        lines.append("-" * 50)
        lines.append(f"  {your_name + ':':<16} {stats['your_text_emoji_total']:,} emojis")
        if stats.get("your_top_text_emojis"):
            top_str = ", ".join(f":{name}: ({count})" for name, count in stats["your_top_text_emojis"])
            lines.append(f"    Top:            {top_str}")
        lines.append(f"  {their_name + ':':<16} {stats['their_text_emoji_total']:,} emojis")
        if stats.get("their_top_text_emojis"):
            top_str = ", ".join(f":{name}: ({count})" for name, count in stats["their_top_text_emojis"])
            lines.append(f"    Top:            {top_str}")

    # Reactions (smaller section)
    has_reactions = (
        stats.get("your_reactions_given", 0) > 0
        or stats.get("their_reactions_given", 0) > 0
    )
    if has_reactions:
        lines.append("")
        lines.append("Reactions on Messages")
        lines.append("-" * 50)
        lines.append(f"  {your_name + ':':<16} {stats['your_reactions_given']:,} given")
        lines.append(f"  {their_name + ':':<16} {stats['their_reactions_given']:,} given")
        if stats.get("top_reactions"):
            top_str = ", ".join(f":{name}: ({count})" for name, count in stats["top_reactions"])
            lines.append(f"  Top:              {top_str}")

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
        sorted_days = sorted(weekday.items(), key=lambda x: DAY_ORDER.index(x[0]) if x[0] in DAY_ORDER else 7)
        lines.append("")
        lines.append("By Day of Week")
        lines.append("-" * 50)
        for day, count in sorted_days:
            lines.append(f"  {day:<12} {count:>8,}")

    lines.append("")
    return "\n".join(lines)
