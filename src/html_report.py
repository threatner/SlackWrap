import json
import os
from datetime import datetime, timezone
from src.report import format_duration

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


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

    # Determine period
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
        period_str = f"{first_date.strftime('%Y-%m-%d')} &rarr; {last_date.strftime('%Y-%m-%d')} ({span_days} days)"

    # Build chart data
    hourly_labels = json.dumps([f"{h:02d}:00" for h in range(24)])
    hourly_data = json.dumps([m_stats.get("hourly_breakdown", {}).get(h, 0) for h in range(24)] if has_messages else [])

    weekday_labels = json.dumps(DAY_ORDER)
    weekday_data = json.dumps([m_stats.get("weekday_breakdown", {}).get(d, 0) for d in DAY_ORDER] if has_messages else [])
    h_weekday_data = json.dumps([h_stats.get("weekday_breakdown", {}).get(d, 0) for d in DAY_ORDER] if has_huddles else [])

    monthly_labels = json.dumps(list(m_stats.get("monthly_breakdown", {}).keys())) if has_messages else "[]"
    monthly_data = json.dumps(list(m_stats.get("monthly_breakdown", {}).values())) if has_messages else "[]"

    # Build cards HTML
    cards = []

    if has_huddles:
        total_hrs = h_stats["total_seconds"] / 3600
        cards.append(_card("Huddle Time", f"""
            <div class="stat-row"><span class="label">Total time</span><span class="value">{format_duration(h_stats['total_seconds'])} <small>({total_hrs:.1f} hours)</small></span></div>
            <div class="stat-row"><span class="label">Total huddles</span><span class="value">{h_stats['total_huddles']}</span></div>
            <div class="stat-row"><span class="label">Average</span><span class="value">{format_duration(h_stats['avg_seconds'])} per huddle</span></div>
            <div class="stat-row"><span class="label">Median</span><span class="value">{format_duration(h_stats['median_seconds'])} per huddle</span></div>
            <div class="stat-row"><span class="label">Longest</span><span class="value">{format_duration(h_stats['longest_seconds'])}</span></div>
            <div class="stat-row"><span class="label">Shortest</span><span class="value">{format_duration(h_stats['shortest_seconds'])}</span></div>
        """))

    if has_messages:
        per_week = m_stats["total_messages"] / max(m_stats["span_days"] / 7, 1) if m_stats["span_days"] > 0 else 0
        cards.append(_card("Messages", f"""
            <div class="stat-row"><span class="label">Total messages</span><span class="value">{m_stats['total_messages']:,}</span></div>
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{m_stats['you_count']:,} ({m_stats['you_pct']:.0f}%)</span></div>
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{m_stats['them_count']:,} ({m_stats['them_pct']:.0f}%)</span></div>
            <div class="stat-row"><span class="label">Per week</span><span class="value">{per_week:.1f} messages</span></div>
        """))

    # Who initiates
    init_rows = ""
    if has_huddles:
        h_total = h_stats["total_huddles"]
        h_you_pct = h_stats["started_by_you"] / h_total * 100 if h_total else 0
        h_them_pct = h_stats["started_by_them"] / h_total * 100 if h_total else 0
        init_rows += f'<div class="stat-row"><span class="label">Huddles</span><span class="value">{your_name}: {h_stats["started_by_you"]} ({h_you_pct:.0f}%) &mdash; {their_name}: {h_stats["started_by_them"]} ({h_them_pct:.0f}%)</span></div>'
    if has_messages:
        m_init_total = m_stats["you_initiated"] + m_stats["them_initiated"]
        if m_init_total > 0:
            m_you_pct = m_stats["you_initiated"] / m_init_total * 100
            m_them_pct = m_stats["them_initiated"] / m_init_total * 100
            init_rows += f'<div class="stat-row"><span class="label">Messages</span><span class="value">{your_name}: {m_stats["you_initiated"]} ({m_you_pct:.0f}%) &mdash; {their_name}: {m_stats["them_initiated"]} ({m_them_pct:.0f}%)</span></div>'
    if init_rows:
        cards.append(_card("Who Initiates", init_rows))

    # Response time
    if has_messages and (m_stats["your_avg_response_seconds"] > 0 or m_stats["their_avg_response_seconds"] > 0):
        cards.append(_card("Response Time", f"""
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{format_duration(m_stats['your_median_response_seconds'])} median, {format_duration(m_stats['your_avg_response_seconds'])} avg</span></div>
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{format_duration(m_stats['their_median_response_seconds'])} median, {format_duration(m_stats['their_avg_response_seconds'])} avg</span></div>
        """))

    # Message style
    if has_messages:
        cards.append(_card("Message Style", f"""
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{m_stats['your_avg_words']:.1f} words avg</span></div>
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{m_stats['their_avg_words']:.1f} words avg</span></div>
        """))

    # Streaks
    if has_messages and m_stats.get("longest_streak_days", 0) > 0:
        streak_start = datetime.fromtimestamp(m_stats["longest_streak_start"], tz=timezone.utc).astimezone()
        streak_end = datetime.fromtimestamp(m_stats["longest_streak_end"], tz=timezone.utc).astimezone()
        streak_html = f"""
            <div class="stat-row"><span class="label">Longest streak</span><span class="value">{m_stats['longest_streak_days']} days <small>({streak_start.strftime('%b %d')} - {streak_end.strftime('%b %d')})</small></span></div>
            <div class="stat-row"><span class="label">Current streak</span><span class="value">{m_stats['current_streak_days']} days</span></div>
        """
        if m_stats.get("longest_gap_seconds", 0) > 0:
            gap_days = m_stats["longest_gap_seconds"] // 86400
            gap_start = datetime.fromtimestamp(m_stats["longest_gap_start"], tz=timezone.utc).astimezone()
            gap_end = datetime.fromtimestamp(m_stats["longest_gap_end"], tz=timezone.utc).astimezone()
            streak_html += f'<div class="stat-row"><span class="label">Longest silence</span><span class="value">{gap_days} days <small>({gap_start.strftime("%b %d")} - {gap_end.strftime("%b %d")})</small></span></div>'
        cards.append(_card("Conversation Streaks", streak_html))

    # First & Last
    if has_messages and m_stats.get("first_message") and m_stats.get("last_message"):
        fm = m_stats["first_message"]
        lm = m_stats["last_message"]
        fm_dt = datetime.fromtimestamp(fm["ts"], tz=timezone.utc).astimezone()
        lm_dt = datetime.fromtimestamp(lm["ts"], tz=timezone.utc).astimezone()
        cards.append(_card("First & Last", f"""
            <div class="stat-row"><span class="label">First message</span><span class="value">{fm_dt.strftime('%Y-%m-%d')}</span></div>
            <div class="quote">&ldquo;{_escape(fm['text'])}&rdquo;</div>
            <div class="stat-row"><span class="label">Last message</span><span class="value">{lm_dt.strftime('%Y-%m-%d')}</span></div>
            <div class="quote">&ldquo;{_escape(lm['text'])}&rdquo;</div>
        """))

    # Emojis in Messages
    has_text_emoji = has_messages and (m_stats.get("your_text_emoji_total", 0) > 0 or m_stats.get("their_text_emoji_total", 0) > 0)
    if has_text_emoji:
        emoji_html = f"""
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{m_stats['your_text_emoji_total']:,} emojis</span></div>
        """
        if m_stats.get("your_top_text_emojis"):
            top_str = " &nbsp; ".join(f":{name}: <small>({count})</small>" for name, count in m_stats["your_top_text_emojis"])
            emoji_html += f'<div class="stat-row"><span class="label"></span><span class="value" style="font-size:12px;color:#8b949e">{top_str}</span></div>'
        emoji_html += f"""
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{m_stats['their_text_emoji_total']:,} emojis</span></div>
        """
        if m_stats.get("their_top_text_emojis"):
            top_str = " &nbsp; ".join(f":{name}: <small>({count})</small>" for name, count in m_stats["their_top_text_emojis"])
            emoji_html += f'<div class="stat-row"><span class="label"></span><span class="value" style="font-size:12px;color:#8b949e">{top_str}</span></div>'
        cards.append(_card("Emojis in Messages", emoji_html))

    # Reactions on Messages
    if has_messages and (m_stats.get("your_reactions_given", 0) > 0 or m_stats.get("their_reactions_given", 0) > 0):
        react_html = f"""
            <div class="stat-row"><span class="label">{your_name}</span><span class="value">{m_stats['your_reactions_given']:,} given</span></div>
            <div class="stat-row"><span class="label">{their_name}</span><span class="value">{m_stats['their_reactions_given']:,} given</span></div>
        """
        if m_stats.get("top_reactions"):
            top_str = " &nbsp; ".join(f":{name}: <small>({count})</small>" for name, count in m_stats["top_reactions"])
            react_html += f'<div class="stat-row" style="margin-top:8px"><span class="label">Top</span><span class="value">{top_str}</span></div>'
        cards.append(_card("Reactions on Messages", react_html))

    cards_html = "\n".join(cards)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Slack Analytics — {_escape(channel_label)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1117; color: #e1e4e8; padding: 40px 20px; }}
.container {{ max-width: 960px; margin: 0 auto; }}
h1 {{ font-size: 28px; font-weight: 600; margin-bottom: 4px; color: #fff; }}
.subtitle {{ color: #8b949e; font-size: 14px; margin-bottom: 32px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 16px; margin-bottom: 24px; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px 24px; }}
.card h2 {{ font-size: 14px; font-weight: 600; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; }}
.stat-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #21262d; }}
.stat-row:last-child {{ border-bottom: none; }}
.stat-row .label {{ color: #8b949e; font-size: 14px; }}
.stat-row .value {{ color: #e1e4e8; font-size: 14px; font-weight: 500; }}
.stat-row .value small {{ color: #8b949e; font-weight: 400; }}
.quote {{ color: #8b949e; font-style: italic; font-size: 13px; padding: 6px 0 10px 16px; border-left: 2px solid #30363d; margin: 4px 0 8px 0; }}
.chart-container {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px 24px; margin-bottom: 16px; }}
.chart-container h2 {{ font-size: 14px; font-weight: 600; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; }}
canvas {{ max-height: 280px; }}
.footer {{ text-align: center; color: #484f58; font-size: 12px; margin-top: 40px; }}
</style>
</head>
<body>
<div class="container">
<h1>Slack Analytics</h1>
<p class="subtitle">{_escape(channel_label)} &nbsp;&bull;&nbsp; {period_str}</p>

<div class="grid">
{cards_html}
</div>

{"" if not has_messages else f'''
<div class="chart-container">
<h2>Messages Over Time</h2>
<canvas id="monthlyChart"></canvas>
</div>
'''}

<div class="grid">
{"" if not has_messages else f'''
<div class="chart-container">
<h2>Activity by Hour</h2>
<canvas id="hourlyChart"></canvas>
</div>
'''}
<div class="chart-container">
<h2>Activity by Day</h2>
<canvas id="weekdayChart"></canvas>
</div>
</div>

<p class="footer">Generated by Huddle Time Tracker</p>
</div>

<script>
const chartDefaults = {{
    color: '#8b949e',
    borderColor: '#30363d',
}};
Chart.defaults.color = chartDefaults.color;
Chart.defaults.borderColor = chartDefaults.borderColor;

{"" if not has_messages else f'''
new Chart(document.getElementById('monthlyChart'), {{
    type: 'bar',
    data: {{
        labels: {monthly_labels},
        datasets: [{{ label: 'Messages', data: {monthly_data}, backgroundColor: '#388bfd', borderRadius: 4 }}]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#21262d' }} }}, x: {{ grid: {{ display: false }} }} }} }}
}});

new Chart(document.getElementById('hourlyChart'), {{
    type: 'bar',
    data: {{
        labels: {hourly_labels},
        datasets: [{{ label: 'Messages', data: {hourly_data}, backgroundColor: '#388bfd', borderRadius: 4 }}]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#21262d' }} }}, x: {{ grid: {{ display: false }} }} }} }}
}});
'''}

// Replace :shortcode: with emoji — map loaded from gemoji CDN
document.addEventListener('DOMContentLoaded', async () => {{
  let emojiMap = {{}};
  try {{
    const resp = await fetch('https://cdn.jsdelivr.net/npm/gemoji/index.json');
    const data = await resp.json();
    for (const [emoji, info] of Object.entries(data)) {{
      if (info.names) info.names.forEach(n => {{ emojiMap[n] = emoji; }});
    }}
  }} catch(e) {{ console.warn('Could not load emoji map:', e); }}
  document.querySelectorAll('.value, .quote').forEach(el => {{
    el.innerHTML = el.innerHTML.replace(/:([a-zA-Z0-9_+-]+):/g, (match, name) => {{
      return emojiMap[name] ? `<span style="font-size:1.2em">${{emojiMap[name]}}</span>` : match;
    }});
  }});
}});

new Chart(document.getElementById('weekdayChart'), {{
    type: 'bar',
    data: {{
        labels: {weekday_labels},
        datasets: [
            {"" if not has_messages else f"{{ label: 'Messages', data: {weekday_data}, backgroundColor: '#388bfd', borderRadius: 4 }},"}
            {"" if not has_huddles else f"{{ label: 'Huddles', data: {h_weekday_data}, backgroundColor: '#f78166', borderRadius: 4 }},"}
        ]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: true, position: 'top' }} }}, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#21262d' }} }}, x: {{ grid: {{ display: false }} }} }} }}
}});
</script>
</body>
</html>"""

    # Write file
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
