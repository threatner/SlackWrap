"""
Plain-text console formatter for WorkspaceStats.
Pure function: takes WorkspaceStats, returns a string.
"""
from datetime import datetime, timezone
from src.engine.models import WorkspaceStats


def _fmt_dur(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def _pct(val: float | None) -> str:
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_workspace_console(ws: WorkspaceStats) -> str:
    lines = []
    w = lines.append

    start = ws.window_start.strftime("%Y-%m-%d")
    end = ws.window_end.strftime("%Y-%m-%d")
    days = (ws.window_end - ws.window_start).days

    w("")
    w("SlackWrap")
    w("=" * 60)
    w(f"  {ws.me.name}")
    w(f"  {start} → {end} ({days} days)")
    w("")

    # Hero
    w("Headline")
    w("-" * 60)
    w(f"  Messages sent:    {ws.hero.total_messages_sent:,}")
    w(f"  Huddle time:      {_fmt_dur(ws.hero.total_huddle_seconds)}")
    w(f"  Humans reached:   {ws.hero.unique_humans}")
    w(f"  Active convos:    {ws.hero.active_conversations}")
    if ws.hero.longest_streak:
        s = ws.hero.longest_streak
        w(f"  Longest streak:   {s.length_days} days ({s.start_date.strftime('%b %d')} – {s.end_date.strftime('%b %d')})")
    if ws.hero.busiest_day:
        b = ws.hero.busiest_day
        w(f"  Busiest day:      {b.date.strftime('%Y-%m-%d')} ({b.message_count} messages)")
    w("")

    # Top People
    if ws.people.top_by_interaction:
        w("Top People (by interaction score)")
        w("-" * 60)
        for i, p in enumerate(ws.people.top_by_interaction, 1):
            parts = []
            if p.dm_messages_exchanged: parts.append(f"{p.dm_messages_exchanged} dm")
            if p.huddle_seconds: parts.append(f"{_fmt_dur(p.huddle_seconds)} huddle")
            if p.thread_coparticipations: parts.append(f"{p.thread_coparticipations} threads")
            detail = " · ".join(parts)
            w(f"  {i:2d}. {p.user.name:<25s} {detail}")
        w("")

    # Top Channels
    if ws.channels.top_by_my_messages:
        w("Top Channels (your messages)")
        w("-" * 60)
        for i, c in enumerate(ws.channels.top_by_my_messages, 1):
            w(f"  {i:2d}. #{c.name:<25s} {c.my_message_count:>5,} yours / {c.total_message_count:>6,} total")
        w("")

    # Huddles
    if ws.huddles.total_huddles > 0:
        w("Huddles")
        w("-" * 60)
        w(f"  Total:            {ws.huddles.total_huddles} huddles, {_fmt_dur(ws.huddles.total_seconds)}")
        w(f"  Average:          {_fmt_dur(int(ws.huddles.avg_seconds))}")
        if ws.huddles.longest_huddle_seconds > 0:
            partner = ws.huddles.longest_huddle_partner.name if ws.huddles.longest_huddle_partner else "?"
            w(f"  Longest:          {_fmt_dur(ws.huddles.longest_huddle_seconds)} with {partner}")
        if ws.huddles.partner_leaderboard:
            w("  Partners:")
            for p in ws.huddles.partner_leaderboard[:5]:
                w(f"    {p.user.name:<25s} {_fmt_dur(p.huddle_seconds)}")
        w("")

    # Mentions
    if ws.mentions.total_mentions_received > 0 or ws.mentions.total_mentions_made > 0:
        w("Mentions")
        w("-" * 60)
        w(f"  Times @mentioned: {ws.mentions.total_mentions_received}")
        w(f"  @mentions made:   {ws.mentions.total_mentions_made}")
        if ws.mentions.top_mentioners_of_me:
            w("  Top mentioners:")
            for mc in ws.mentions.top_mentioners_of_me[:5]:
                w(f"    {mc.user.name:<25s} {mc.count} times")
        if ws.mentions.top_people_i_mentioned:
            w("  You mention most:")
            for mc in ws.mentions.top_people_i_mentioned[:5]:
                w(f"    {mc.user.name:<25s} {mc.count} times")
        w("")

    # Trends
    w("Trends")
    w("-" * 60)
    w(f"  Messages:         {_pct(ws.trends.message_volume_change_pct)} vs prior period")
    w(f"  Huddle time:      {_pct(ws.trends.huddle_time_change_pct)} vs prior period")
    w(f"  People:           {ws.trends.unique_people_change:+d} vs prior period")
    if ws.trends.most_active_month:
        m = ws.trends.most_active_month
        w(f"  Most active:      {MONTH_NAMES[m.month]} {m.year} ({m.message_count:,} msgs)")
    if ws.trends.quietest_month:
        m = ws.trends.quietest_month
        w(f"  Quietest:         {MONTH_NAMES[m.month]} {m.year} ({m.message_count:,} msgs)")
    w("")

    # Top Words
    if ws.messages.top_words:
        w("Your Top Words")
        w("-" * 60)
        words_str = ", ".join(f"{word} ({count})" for word, count in ws.messages.top_words[:10])
        w(f"  {words_str}")
        w("")

    # Bookends
    if ws.messages.first_message or ws.messages.last_message:
        w("Bookends")
        w("-" * 60)
        if ws.messages.first_message:
            fm = ws.messages.first_message
            dt = datetime.fromtimestamp(fm.ts, tz=timezone.utc).astimezone()
            w(f"  First:  {dt.strftime('%Y-%m-%d')} in {fm.conversation_name}")
            w(f"          \"{fm.text_preview}\"")
        if ws.messages.last_message:
            lm = ws.messages.last_message
            dt = datetime.fromtimestamp(lm.ts, tz=timezone.utc).astimezone()
            w(f"  Last:   {dt.strftime('%Y-%m-%d')} in {lm.conversation_name}")
            w(f"          \"{lm.text_preview}\"")
        w("")

    if ws.failed_conversations:
        w(f"Failed ({len(ws.failed_conversations)})")
        w("-" * 60)
        for cid, err in ws.failed_conversations:
            w(f"  {cid}: {err}")
        w("")

    return "\n".join(lines)
