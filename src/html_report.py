import json
import os
from datetime import datetime, timezone
from src.report import format_duration, DAY_ORDER, format_pct_change, format_month_label

DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def generate_html_report(
    h_stats: dict | None,
    m_stats: dict | None,
    channel_label: str,
    your_name: str = "You",
    their_name: str = "Them",
    output_dir: str = ".",
) -> str:
    has_huddles = h_stats is not None and h_stats.get("total_huddles", 0) > 0
    has_messages = m_stats is not None and m_stats.get("total_messages", 0) > 0

    # Period
    all_ts = []
    if has_huddles:
        all_ts.extend(h["room"]["date_start"] for h in h_stats["huddles"])
    if has_messages and m_stats["first_ts"]:
        all_ts.extend([m_stats["first_ts"], m_stats["last_ts"]])

    period_str = ""
    span_days = 1
    if all_ts:
        first_date = datetime.fromtimestamp(min(all_ts), tz=timezone.utc).astimezone()
        last_date = datetime.fromtimestamp(max(all_ts), tz=timezone.utc).astimezone()
        span_days = (last_date - first_date).days + 1
        period_str = f"{first_date.strftime('%b %d, %Y')} &rarr; {last_date.strftime('%b %d, %Y')}"

    # Chart data
    hourly_labels = json.dumps([f"{h:02d}:00" for h in range(24)])
    hourly_data = json.dumps([m_stats.get("hourly_breakdown", {}).get(h, 0) for h in range(24)] if has_messages else [])

    weekday_labels = json.dumps(DAY_SHORT)
    weekday_data = json.dumps([m_stats.get("weekday_breakdown", {}).get(d, 0) for d in DAY_ORDER] if has_messages else [])
    h_weekday_data = json.dumps([h_stats.get("weekday_breakdown", {}).get(d, 0) for d in DAY_ORDER] if has_huddles else [])

    monthly_labels = json.dumps(list(m_stats.get("monthly_breakdown", {}).keys())) if has_messages else "[]"
    monthly_data = json.dumps(list(m_stats.get("monthly_breakdown", {}).values())) if has_messages else "[]"

    resp_by_hour = m_stats.get("response_time_by_hour", {}) if has_messages else {}

    msg_split_data = json.dumps([m_stats["you_count"], m_stats["them_count"]]) if has_messages else "[]"
    msg_split_labels = json.dumps([your_name, their_name])

    # Hero stats
    hero_items = []
    if has_huddles:
        total_hrs = h_stats["total_seconds"] / 3600
        hero_items.append(("Huddle Time", format_duration(h_stats["total_seconds"]), f"{total_hrs:.1f} hours"))
        hero_items.append(("Huddles", str(h_stats["total_huddles"]), f"avg {format_duration(h_stats['avg_seconds'])} each"))
    if has_messages:
        hero_items.append(("Messages", f"{m_stats['total_messages']:,}", f"{span_days:,} days"))
        if m_stats.get("longest_streak_days", 0) > 0:
            hero_items.append(("Best Streak", f"{m_stats['longest_streak_days']} days", f"current: {m_stats['current_streak_days']}d"))

    hero_html = ""
    for title, big, sub in hero_items:
        hero_html += f'<div class="hero-item"><div class="hero-value">{big}</div><div class="hero-label">{title}</div><div class="hero-sub">{sub}</div></div>\n'

    # Detail cards
    cards = []

    # Who starts huddles
    if has_huddles:
        h_total = h_stats["total_huddles"]
        h_you_pct = h_stats["started_by_you"] / h_total * 100 if h_total else 0
        h_them_pct = h_stats["started_by_them"] / h_total * 100 if h_total else 0
        cards.append(_card("Who Starts Huddles", f"""
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{h_stats["started_by_you"]} ({h_you_pct:.0f}%)</span></div>
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{h_stats["started_by_them"]} ({h_them_pct:.0f}%)</span></div>
        """))

    # Response time
    if has_messages and (m_stats["your_avg_response_seconds"] > 0 or m_stats["their_avg_response_seconds"] > 0):
        cards.append(_card("Response Time", f"""
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{format_duration(m_stats['your_median_response_seconds'])} <small>median</small> &middot; {format_duration(m_stats['your_avg_response_seconds'])} <small>avg</small></span></div>
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{format_duration(m_stats['their_median_response_seconds'])} <small>median</small> &middot; {format_duration(m_stats['their_avg_response_seconds'])} <small>avg</small></span></div>
        """))

    # Huddle details
    if has_huddles:
        cards.append(_card("Huddle Details", f"""
            <div class="stat-row"><span class="label">Average</span><span class="value">{format_duration(h_stats['avg_seconds'])}</span></div>
            <div class="stat-row"><span class="label">Median</span><span class="value">{format_duration(h_stats['median_seconds'])}</span></div>
            <div class="stat-row"><span class="label">Longest</span><span class="value">{format_duration(h_stats['longest_seconds'])}</span></div>
            <div class="stat-row"><span class="label">Shortest</span><span class="value">{format_duration(h_stats['shortest_seconds'])}</span></div>
        """))

    # Message style
    if has_messages:
        cards.append(_card("Message Style", f"""
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{m_stats['your_avg_words']:.1f} words avg</span></div>
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{m_stats['their_avg_words']:.1f} words avg</span></div>
        """))

    # Streaks & dead zones
    if has_messages and (m_stats.get("longest_streak_days", 0) > 0 or m_stats.get("longest_gap_seconds", 0) > 0):
        streak_html = ""
        if m_stats.get("longest_streak_days", 0) > 0:
            s_start = datetime.fromtimestamp(m_stats["longest_streak_start"], tz=timezone.utc).astimezone()
            s_end = datetime.fromtimestamp(m_stats["longest_streak_end"], tz=timezone.utc).astimezone()
            streak_html += f'<div class="stat-row"><span class="label">Longest streak</span><span class="value">{m_stats["longest_streak_days"]} days <small>{s_start.strftime("%b %d")} - {s_end.strftime("%b %d")}</small></span></div>'
            streak_html += f'<div class="stat-row"><span class="label">Current streak</span><span class="value">{m_stats["current_streak_days"]} days</span></div>'
        if m_stats.get("longest_gap_seconds", 0) > 0:
            gap_days = m_stats["longest_gap_seconds"] // 86400
            g_start = datetime.fromtimestamp(m_stats["longest_gap_start"], tz=timezone.utc).astimezone()
            g_end = datetime.fromtimestamp(m_stats["longest_gap_end"], tz=timezone.utc).astimezone()
            streak_html += f'<div class="stat-row"><span class="label">Longest silence</span><span class="value">{gap_days} days <small>{g_start.strftime("%b %d")} - {g_end.strftime("%b %d")}</small></span></div>'
        cards.append(_card("Streaks & Silences", streak_html))

    # First & Last
    if has_messages and m_stats.get("first_message") and m_stats.get("last_message"):
        fm = m_stats["first_message"]
        lm = m_stats["last_message"]
        fm_dt = datetime.fromtimestamp(fm["ts"], tz=timezone.utc).astimezone()
        lm_dt = datetime.fromtimestamp(lm["ts"], tz=timezone.utc).astimezone()
        cards.append(_card("First & Last Message", f"""
            <div class="stat-row"><span class="label">First</span><span class="value">{fm_dt.strftime('%b %d, %Y')}</span></div>
            <div class="quote">&ldquo;{_escape(fm['text'])}&rdquo;</div>
            <div class="stat-row"><span class="label">Last</span><span class="value">{lm_dt.strftime('%b %d, %Y')}</span></div>
            <div class="quote">&ldquo;{_escape(lm['text'])}&rdquo;</div>
        """))

    # Emojis in messages
    has_text_emoji = has_messages and (m_stats.get("your_text_emoji_total", 0) > 0 or m_stats.get("their_text_emoji_total", 0) > 0)
    if has_text_emoji:
        emoji_html = f'<div class="stat-row"><span class="label">{your_name}</span><span class="value">{m_stats["your_text_emoji_total"]:,} emojis</span></div>'
        if m_stats.get("your_top_text_emojis"):
            top_str = " ".join(f'<span class="emoji-badge">:{name}: <small>{count}</small></span>' for name, count in m_stats["your_top_text_emojis"])
            emoji_html += f'<div class="emoji-row">{top_str}</div>'
        emoji_html += f'<div class="stat-row"><span class="label">{their_name}</span><span class="value">{m_stats["their_text_emoji_total"]:,} emojis</span></div>'
        if m_stats.get("their_top_text_emojis"):
            top_str = " ".join(f'<span class="emoji-badge">:{name}: <small>{count}</small></span>' for name, count in m_stats["their_top_text_emojis"])
            emoji_html += f'<div class="emoji-row">{top_str}</div>'
        cards.append(_card("Emojis in Messages", emoji_html))

    # Response Time by Hour (card — fastest/slowest)
    if has_messages and resp_by_hour:
        fastest_hour = min(resp_by_hour, key=resp_by_hour.get)
        slowest_hour = max(resp_by_hour, key=resp_by_hour.get)
        cards.append(_card("Response Time by Hour", f"""
            <div class="stat-row"><span class="label">Fastest</span><span class="value">{fastest_hour:02d}:00 <small>{format_duration(resp_by_hour[fastest_hour])} median</small></span></div>
            <div class="stat-row"><span class="label">Slowest</span><span class="value">{slowest_hour:02d}:00 <small>{format_duration(resp_by_hour[slowest_hour])} median</small></span></div>
        """))

    # Links & Files
    if has_messages:
        your_links = m_stats.get("your_links_shared", 0)
        their_links = m_stats.get("their_links_shared", 0)
        your_files = m_stats.get("your_files_shared", 0)
        their_files = m_stats.get("their_files_shared", 0)
        if your_links > 0 or their_links > 0 or your_files > 0 or their_files > 0:
            cards.append(_card("Links & Files", f"""
                <div class="stat-row"><span class="label">{your_name}</span><span class="value">{your_links} links &middot; {your_files} files</span></div>
                <div class="stat-row"><span class="label">{their_name}</span><span class="value">{their_links} links &middot; {their_files} files</span></div>
            """))

    # Thread Activity
    if has_messages and m_stats.get("top_level_messages") is not None:
        top_lvl = m_stats.get("top_level_messages", 0)
        thr_msgs = m_stats.get("thread_messages", 0)
        thr_pct = m_stats.get("thread_pct", 0.0)
        top_pct = round(top_lvl / m_stats["total_messages"] * 100) if m_stats["total_messages"] else 0
        you_started = m_stats.get("threads_started_by_you", 0)
        them_started = m_stats.get("threads_started_by_them", 0)
        thread_html = f"""
            <div class="stat-row"><span class="label">Top-level</span><span class="value">{top_lvl:,} <small>({top_pct}%)</small></span></div>
            <div class="stat-row"><span class="label">In threads</span><span class="value">{thr_msgs:,} <small>({round(thr_pct)}%)</small></span></div>
        """
        if you_started > 0 or them_started > 0:
            thread_html += f'<div class="stat-row"><span class="label">Threads started</span><span class="value">{your_name}: {you_started} &middot; {their_name}: {them_started}</span></div>'
        cards.append(_card("Thread Activity", thread_html))

    # Trends
    if has_messages and m_stats.get("trend_last_30d_count") is not None:
        pct_30d_str = format_pct_change(m_stats.get("trend_30d_pct_change"))
        pct_yoy_str = format_pct_change(m_stats.get("trend_yoy_pct_change"))
        current_month_display = format_month_label(m_stats.get("trend_current_month", ""))
        yoy_label = m_stats.get("trend_yoy_month", "")
        yoy_display = format_month_label(yoy_label) if yoy_label else "prior year"
        trend_html = f"""
            <div class="stat-row"><span class="label">Last 30 days</span><span class="value">{m_stats['trend_last_30d_count']:,} messages <small>{pct_30d_str} vs prev 30d</small></span></div>
            <div class="stat-row"><span class="label">{_escape(current_month_display)}</span><span class="value">{m_stats['trend_current_month_count']:,} messages <small>{pct_yoy_str} daily avg vs {_escape(yoy_display)}</small></span></div>
        """
        cards.append(_card("Trends", trend_html))

    # Reactions
    if has_messages and (m_stats.get("your_reactions_given", 0) > 0 or m_stats.get("their_reactions_given", 0) > 0):
        react_html = f"""
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{m_stats['your_reactions_given']:,} reactions</span></div>
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{m_stats['their_reactions_given']:,} reactions</span></div>
        """
        if m_stats.get("top_reactions"):
            top_str = " ".join(f'<span class="emoji-badge">:{name}: <small>{count}</small></span>' for name, count in m_stats["top_reactions"])
            react_html += f'<div class="emoji-row">{top_str}</div>'
        cards.append(_card("Reactions", react_html))

    cards_html = "\n".join(cards)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Slack Analytics - {_escape(channel_label)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg: #0d1117; --card: #161b22; --border: #30363d; --border-subtle: #21262d;
  --text: #e6edf3; --text-muted: #8b949e; --text-dim: #484f58;
  --blue: #58a6ff; --blue-bg: rgba(56,139,253,0.15);
  --orange: #f78166; --orange-bg: rgba(247,129,102,0.15);
  --green: #3fb950; --green-bg: rgba(63,185,80,0.15);
  --purple: #bc8cff;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}

.container {{ max-width: 1080px; margin: 0 auto; padding: 48px 24px 64px; }}

/* Header */
.header {{ margin-bottom: 40px; }}
.header h1 {{ font-size: 32px; font-weight: 700; color: #fff; margin-bottom: 6px; }}
.header .meta {{ color: var(--text-muted); font-size: 15px; }}
.header .meta .period {{ color: var(--text-dim); }}

/* Hero stats */
.hero {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.hero-item {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 24px; text-align: center; }}
.hero-value {{ font-size: 36px; font-weight: 700; color: #fff; line-height: 1.1; margin-bottom: 6px; }}
.hero-label {{ font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 2px; }}
.hero-sub {{ font-size: 12px; color: var(--text-dim); }}

/* Section headers */
.section-title {{ font-size: 13px; font-weight: 600; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin: 36px 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border-subtle); }}

/* Card grid */
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap: 16px; margin-bottom: 8px; }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 24px 28px; }}
.card h2 {{ font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 16px; }}
.stat-row {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--border-subtle); }}
.stat-row:last-child {{ border-bottom: none; }}
.stat-row .label {{ color: var(--text-muted); font-size: 14px; min-width: 100px; }}
.stat-row .value {{ color: var(--text); font-size: 14px; font-weight: 500; text-align: right; }}
.stat-row .value small {{ color: var(--text-muted); font-weight: 400; font-size: 12px; }}
.quote {{ color: var(--text-dim); font-style: italic; font-size: 13px; padding: 8px 0 12px 16px; border-left: 2px solid var(--border); margin: 2px 0 6px; line-height: 1.5; }}
.emoji-row {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 0 4px; }}
.emoji-badge {{ background: var(--blue-bg); border-radius: 8px; padding: 4px 10px; font-size: 14px; white-space: nowrap; }}
.emoji-badge small {{ color: var(--text-muted); font-size: 11px; margin-left: 2px; }}

/* Charts */
.chart-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 28px; margin-bottom: 16px; }}
.chart-card h2 {{ font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 20px; }}
.chart-card canvas {{ max-height: 300px; }}
.chart-grid {{ display: grid; grid-template-columns: {"1fr 1fr" if has_messages else "1fr"}; gap: 16px; margin-bottom: 8px; }}
.chart-split {{ display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 8px; }}

/* Footer */
.footer {{ text-align: center; color: var(--text-dim); font-size: 12px; margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--border-subtle); }}

@media (max-width: 600px) {{
  .grid {{ grid-template-columns: 1fr; }}
  .chart-grid {{ grid-template-columns: 1fr; }}
  .chart-split {{ grid-template-columns: 1fr; }}
  .hero {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>{_escape(channel_label)}</h1>
  <p class="meta">Slack Analytics <span class="period">&middot; {period_str} &middot; {span_days:,} days</span></p>
</div>

<div class="hero">
{hero_html}
</div>

{"" if not has_messages else f'''
<div class="section-title">Activity Over Time</div>
<div class="chart-card">
  <h2>Messages per Month</h2>
  <canvas id="monthlyChart"></canvas>
</div>
'''}

<div class="section-title">Activity Patterns</div>
{"" if not has_messages else f'''
<div class="chart-split">
  <div class="chart-card">
    <h2>By Hour of Day</h2>
    <canvas id="hourlyChart"></canvas>
  </div>
  <div class="chart-card">
    <h2>Message Split</h2>
    <canvas id="splitChart"></canvas>
  </div>
</div>
'''}

<div class="chart-card">
  <h2>By Day of Week</h2>
  <canvas id="weekdayChart"></canvas>
</div>


<div class="section-title">Details</div>
<div class="grid">
{cards_html}
</div>

<p class="footer">Generated by Huddle Time Tracker</p>
</div>

<script>
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#21262d';
Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

{"" if not has_messages else f'''
new Chart(document.getElementById('monthlyChart'), {{
  type: 'line',
  data: {{
    labels: {monthly_labels},
    datasets: [{{
      label: 'Messages',
      data: {monthly_data},
      borderColor: '#58a6ff',
      backgroundColor: 'rgba(56,139,253,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: 3,
      pointBackgroundColor: '#58a6ff',
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#161b22' }} }}, x: {{ grid: {{ display: false }} }} }}
  }}
}});

new Chart(document.getElementById('hourlyChart'), {{
  type: 'bar',
  data: {{
    labels: {hourly_labels},
    datasets: [{{
      label: 'Messages',
      data: {hourly_data},
      backgroundColor: 'rgba(56,139,253,0.6)',
      borderRadius: 6,
      borderSkipped: false,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#161b22' }} }}, x: {{ grid: {{ display: false }}, ticks: {{ maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }} }} }}
  }}
}});

new Chart(document.getElementById('splitChart'), {{
  type: 'doughnut',
  data: {{
    labels: {msg_split_labels},
    datasets: [{{
      data: {msg_split_data},
      backgroundColor: ['#58a6ff', '#f78166'],
      borderWidth: 0,
      spacing: 3,
    }}]
  }},
  options: {{
    responsive: true,
    cutout: '65%',
    plugins: {{
      legend: {{ display: true, position: 'bottom', labels: {{ padding: 16, usePointStyle: true, pointStyle: 'circle' }} }}
    }}
  }}
}});
'''}

new Chart(document.getElementById('weekdayChart'), {{
  type: 'bar',
  data: {{
    labels: {weekday_labels},
    datasets: [
      {"" if not has_messages else f"{{ label: 'Messages', data: {weekday_data}, backgroundColor: 'rgba(56,139,253,0.6)', borderRadius: 6, borderSkipped: false, yAxisID: 'y' }},"}
      {"" if not has_huddles else f"{{ label: 'Huddles', data: {h_weekday_data}, backgroundColor: 'rgba(247,129,102,0.7)', borderRadius: 6, borderSkipped: false, yAxisID: 'y1' }},"}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: true, position: 'top', labels: {{ padding: 16, usePointStyle: true, pointStyle: 'circle' }} }} }},
    scales: {{
      y: {{ beginAtZero: true, position: 'left', grid: {{ color: '#161b22' }}, title: {{ display: true, text: 'Messages', color: '#58a6ff', font: {{ size: 11 }} }} }},
      y1: {{ beginAtZero: true, position: 'right', grid: {{ drawOnChartArea: false }}, title: {{ display: true, text: 'Huddles', color: '#f78166', font: {{ size: 11 }} }} }},
      x: {{ grid: {{ display: false }} }}
    }}
  }}
}});

// Emoji rendering via gemoji CDN
document.addEventListener('DOMContentLoaded', async () => {{
  let emojiMap = {{}};
  try {{
    const resp = await fetch('https://cdn.jsdelivr.net/npm/gemoji/index.json');
    const data = await resp.json();
    for (const [emoji, info] of Object.entries(data)) {{
      if (info.names) info.names.forEach(n => {{ emojiMap[n] = emoji; }});
    }}
  }} catch(e) {{}}
  document.querySelectorAll('.value, .quote, .emoji-badge').forEach(el => {{
    el.innerHTML = el.innerHTML.replace(/:([a-zA-Z0-9_+-]+):/g, (match, name) => {{
      return emojiMap[name] ? `<span style="font-size:1.15em">${{emojiMap[name]}}</span>` : match;
    }});
  }});
}});
</script>
</body>
</html>"""

    safe_name = channel_label.replace(" ", "_").replace("#", "").replace("(", "").replace(")", "")
    filename = f"slack_analytics_{safe_name}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w") as f:
        f.write(html)
    return filepath


def _card(title: str, content: str) -> str:
    return f'<div class="card"><h2>{title}</h2>{content}</div>'


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
