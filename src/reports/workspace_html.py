"""
Polished single-file HTML workspace wrap report.

render_workspace_html(ws: WorkspaceStats) -> str

Self-contained: Chart.js via CDN, inline CSS, inline SVG heatmap.
Dark theme. Hero tiles + dashboard cards.
"""
import json
import html as html_mod
from datetime import datetime, timezone
from src.engine.models import WorkspaceStats

MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _esc(s: str) -> str:
    return html_mod.escape(str(s))


def _fmt_dur(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def _pct_badge(val: float | None) -> str:
    if val is None:
        return '<span class="badge neutral">—</span>'
    sign = "+" if val >= 0 else ""
    cls = "up" if val >= 0 else "down"
    return f'<span class="badge {cls}">{sign}{val:.1f}%</span>'


def _render_heatmap(data: dict[tuple[int, int], int]) -> str:
    """Render a 7x24 SVG heatmap for day-of-week × hour-of-day."""
    if not data:
        return '<div class="empty-state">No activity data</div>'

    max_val = max(data.values()) if data else 1
    cell_w, cell_h, gap = 18, 18, 2
    label_w = 32
    header_h = 16
    w = label_w + 24 * (cell_w + gap)
    h = header_h + 7 * (cell_h + gap)

    svg = [f'<svg viewBox="0 0 {w} {h}" class="heatmap-svg">']

    # Hour labels
    for hour in range(24):
        x = label_w + hour * (cell_w + gap) + cell_w // 2
        if hour % 3 == 0:
            svg.append(f'<text x="{x}" y="{header_h - 4}" class="heatmap-label">{hour}</text>')

    # Cells
    for dow in range(7):
        y = header_h + dow * (cell_h + gap)
        svg.append(f'<text x="0" y="{y + cell_h - 4}" class="heatmap-label">{DOW_NAMES[dow]}</text>')
        for hour in range(24):
            x = label_w + hour * (cell_w + gap)
            val = data.get((dow, hour), 0)
            opacity = round(val / max_val, 2) if max_val else 0
            opacity = max(opacity, 0.05)
            color = f"rgba(99, 179, 237, {opacity})"
            svg.append(
                f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" '
                f'rx="3" fill="{color}"><title>{DOW_NAMES[dow]} {hour}:00 — {val} msgs</title></rect>'
            )

    svg.append('</svg>')
    return '\n'.join(svg)


def _render_leaderboard(items: list, columns: list[str], formatters: list) -> str:
    """Generic leaderboard table."""
    if not items:
        return '<div class="empty-state">No data</div>'

    rows = []
    for i, item in enumerate(items, 1):
        cells = [f'<td class="rank">{i}</td>']
        for fmt in formatters:
            cells.append(f'<td>{fmt(item)}</td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')

    header = "".join(f'<th>{c}</th>' for c in ["#"] + columns)
    return f'<table><tr>{header}</tr>{"".join(rows)}</table>'


def render_workspace_html(ws: WorkspaceStats) -> str:
    start = ws.window_start.strftime("%b %d, %Y")
    end = ws.window_end.strftime("%b %d, %Y")
    days = (ws.window_end - ws.window_start).days
    me_name = _esc(ws.me.name)

    # Chart data — aggregate to weekly buckets to avoid lag with 100+ daily bars
    from collections import defaultdict
    weekly_buckets: dict[str, int] = defaultdict(int)
    for d, c in ws.messages.daily_volume_timeline:
        # ISO week start (Monday)
        week_start = d - __import__("datetime").timedelta(days=d.weekday())
        label = f"{week_start.strftime('%b %d')}"
        weekly_buckets[label] += c
    timeline_dates = list(weekly_buckets.keys())
    timeline_counts = list(weekly_buckets.values())

    # Heatmap SVG
    heatmap_svg = _render_heatmap(ws.messages.dow_hour_heatmap)

    # People leaderboard
    def _person_name(p):
        return f'<span class="person-chip">{_esc(p.user.name)}</span>'

    def _person_score(p):
        parts = []
        if p.dm_messages_exchanged:
            parts.append(f'{p.dm_messages_exchanged:,} dm')
        if p.huddle_seconds:
            parts.append(f'{_fmt_dur(p.huddle_seconds)} huddle')
        if p.thread_coparticipations:
            parts.append(f'{p.thread_coparticipations} threads')
        return '<span class="metric-detail">' + ' · '.join(parts) + '</span>'

    people_table = _render_leaderboard(
        ws.people.top_by_interaction, ["Person", "Interaction"],
        [_person_name, _person_score],
    )

    # Channel leaderboard
    channels_table = _render_leaderboard(
        ws.channels.top_by_my_messages, ["Channel", "Yours", "Total"],
        [
            lambda c: f'<span class="channel-chip">#{_esc(c.name)}</span>',
            lambda c: f'<span class="metric">{c.my_message_count:,}</span>',
            lambda c: f'<span class="metric dim">{c.total_message_count:,}</span>',
        ],
    )

    # Huddle partners
    huddle_table = _render_leaderboard(
        ws.huddles.partner_leaderboard[:5], ["Partner", "Time"],
        [_person_name, lambda p: f'<span class="metric">{_fmt_dur(p.huddle_seconds)}</span>'],
    )

    # Mention tables
    mentioners_table = _render_leaderboard(
        ws.mentions.top_mentioners_of_me[:5], ["Person", "Times"],
        [lambda mc: f'<span class="person-chip">{_esc(mc.user.name)}</span>',
         lambda mc: f'<span class="metric">{mc.count}</span>'],
    )
    mentioned_table = _render_leaderboard(
        ws.mentions.top_people_i_mentioned[:5], ["Person", "Times"],
        [lambda mc: f'<span class="person-chip">{_esc(mc.user.name)}</span>',
         lambda mc: f'<span class="metric">{mc.count}</span>'],
    )

    # Top words
    words_html = ""
    if ws.messages.top_words:
        words_html = " ".join(
            f'<span class="tag">{_esc(w)} <span class="tag-count">{c}</span></span>'
            for w, c in ws.messages.top_words
        )

    # Top emojis
    emojis_html = ""
    if ws.messages.top_emojis_in_text:
        emojis_html = " ".join(
            f'<span class="tag">:{_esc(e)}: <span class="tag-count">{c}</span></span>'
            for e, c in ws.messages.top_emojis_in_text
        )

    # Bookend helper
    def _bookend(label, msg):
        if not msg:
            return ""
        dt = datetime.fromtimestamp(msg.ts, tz=timezone.utc).astimezone()
        return f'''
        <div class="bookend">
            <div class="bookend-label">{label}</div>
            <div class="bookend-date">{dt.strftime("%b %d, %Y")} in {_esc(msg.conversation_name)}</div>
            <div class="bookend-text">"{_esc(msg.text_preview)}"</div>
        </div>'''

    # Streak / busiest
    streak_text = ""
    if ws.hero.longest_streak:
        s = ws.hero.longest_streak
        streak_text = f"{s.length_days} days<br><span class='tile-sub'>{s.start_date.strftime('%b %d')} – {s.end_date.strftime('%b %d')}</span>"
    busiest_text = ""
    if ws.hero.busiest_day:
        b = ws.hero.busiest_day
        busiest_text = f"{b.message_count}<br><span class='tile-sub'>{b.date.strftime('%b %d, %Y')}</span>"

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SlackWrap — {me_name}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
    --bg: #0a0a1a;
    --surface: #12122a;
    --surface-2: #1a1a3e;
    --border: #252550;
    --text: #e2e2f0;
    --text-dim: #7a7a9e;
    --accent: #63b3ed;
    --accent-2: #9f7aea;
    --accent-3: #f6ad55;
    --green: #68d391;
    --red: #fc8181;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.5; }}

/* Header */
.header {{ background: linear-gradient(135deg, #12122a 0%, #1a103a 50%, #0a0a1a 100%); padding: 48px 24px 32px; text-align: center; position: relative; overflow: hidden; }}
.header::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: radial-gradient(ellipse at 50% 0%, rgba(99,179,237,0.08) 0%, transparent 70%); }}
.header h1 {{ font-size: 2.8em; font-weight: 800; background: linear-gradient(135deg, var(--accent), var(--accent-2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; position: relative; letter-spacing: -0.02em; }}
.header .subtitle {{ color: var(--text-dim); font-size: 1.1em; margin-top: 8px; position: relative; }}

/* Hero tiles */
.hero {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; padding: 24px; max-width: 1200px; margin: -24px auto 0; position: relative; z-index: 1; }}
.tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 24px 16px; text-align: center; transition: transform 0.2s, box-shadow 0.2s; }}
.tile:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.3); }}
.tile-value {{ font-size: 2em; font-weight: 700; color: var(--accent); line-height: 1.1; }}
.tile-label {{ font-size: 0.78em; color: var(--text-dim); margin-top: 6px; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 500; }}
.tile-sub {{ font-size: 0.65em; color: var(--text-dim); font-weight: 400; }}

/* Trends banner */
.trends-banner {{ display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; padding: 16px 24px; max-width: 1200px; margin: 16px auto; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; }}
.trend-item {{ text-align: center; min-width: 120px; }}
.trend-big {{ font-size: 1.2em; font-weight: 600; color: var(--accent); }}
.trend-small {{ font-size: 0.75em; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; font-weight: 600; }}
.badge.up {{ background: rgba(104,211,145,0.15); color: var(--green); }}
.badge.down {{ background: rgba(252,129,129,0.15); color: var(--red); }}
.badge.neutral {{ background: rgba(122,122,158,0.15); color: var(--text-dim); }}

/* Section */
.section {{ max-width: 1200px; margin: 24px auto; padding: 0 24px; }}
.section-title {{ color: var(--accent); font-size: 1.2em; font-weight: 600; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }}

/* Cards grid */
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 20px; }}
.card h3 {{ color: var(--text); font-size: 0.95em; font-weight: 600; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}

/* Tables */
table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
th {{ text-align: left; color: var(--text-dim); font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.5px; padding: 6px 8px; border-bottom: 1px solid var(--border); font-weight: 500; }}
td {{ padding: 8px; border-bottom: 1px solid rgba(37,37,80,0.5); vertical-align: middle; }}
.rank {{ color: var(--accent-2); font-weight: 700; width: 28px; font-size: 0.85em; }}
.person-chip {{ color: var(--text); font-weight: 500; }}
.channel-chip {{ color: var(--accent-3); font-weight: 500; }}
.metric {{ color: var(--accent); font-variant-numeric: tabular-nums; font-weight: 600; }}
.metric.dim {{ color: var(--text-dim); font-weight: 400; }}
.metric-detail {{ color: var(--text-dim); font-size: 0.85em; }}

/* Chart */
.chart-wrap {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 20px; margin-bottom: 16px; }}
.chart-wrap h3 {{ color: var(--text); font-size: 0.95em; font-weight: 600; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}

/* Heatmap */
.heatmap-svg {{ width: 100%; height: auto; }}
.heatmap-svg text {{ fill: var(--text-dim); font-size: 9px; font-family: inherit; }}
.heatmap-svg .heatmap-label {{ font-size: 9px; }}

/* Tags */
.tags {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.tag {{ background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 4px 12px; font-size: 0.85em; color: var(--text); }}
.tag-count {{ color: var(--accent); font-weight: 600; margin-left: 4px; }}

/* Bookends */
.bookend {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 20px; margin-bottom: 12px; }}
.bookend-label {{ font-size: 0.75em; color: var(--accent-2); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }}
.bookend-date {{ color: var(--accent); font-size: 0.85em; margin-top: 4px; }}
.bookend-text {{ color: var(--text-dim); font-style: italic; margin-top: 4px; }}

/* Empty state */
.empty-state {{ color: var(--text-dim); font-style: italic; padding: 12px 0; }}

/* Footer */
.footer {{ text-align: center; padding: 40px 24px; color: var(--text-dim); font-size: 0.75em; }}

/* Stats row */
.stats-row {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 16px; }}
.stat-pill {{ background: var(--surface-2); border-radius: 10px; padding: 8px 16px; }}
.stat-pill .val {{ font-size: 1.1em; font-weight: 600; color: var(--accent); }}
.stat-pill .lbl {{ font-size: 0.75em; color: var(--text-dim); }}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
    <h1>SlackWrap</h1>
    <div class="subtitle">{me_name} &middot; {start} → {end} &middot; {days} days</div>
</div>

<!-- Hero Tiles -->
<div class="hero">
    <div class="tile">
        <div class="tile-value">{ws.hero.total_messages_sent:,}</div>
        <div class="tile-label">Messages Sent</div>
    </div>
    <div class="tile">
        <div class="tile-value">{_fmt_dur(ws.hero.total_huddle_seconds)}</div>
        <div class="tile-label">Huddle Time</div>
    </div>
    <div class="tile">
        <div class="tile-value">{ws.hero.unique_humans}</div>
        <div class="tile-label">Humans Reached</div>
    </div>
    <div class="tile">
        <div class="tile-value">{ws.hero.active_conversations}</div>
        <div class="tile-label">Active Convos</div>
    </div>
    <div class="tile">
        <div class="tile-value">{streak_text or "—"}</div>
        <div class="tile-label">Longest Streak</div>
    </div>
    <div class="tile">
        <div class="tile-value">{busiest_text or "—"}</div>
        <div class="tile-label">Busiest Day</div>
    </div>
</div>

<!-- Trends Banner -->
<div class="section">
    <div class="trends-banner">
        <div class="trend-item">
            <div class="trend-big">{ws.mentions.total_mentions_received:,}</div>
            <div class="trend-small">Times @mentioned</div>
        </div>
        <div class="trend-item">
            <div class="trend-big">{ws.mentions.total_mentions_made:,}</div>
            <div class="trend-small">@mentions Made</div>
        </div>
        <div class="trend-item">
            <div class="trend-big">{ws.huddles.total_huddles}</div>
            <div class="trend-small">Huddles</div>
        </div>
        <div class="trend-item">
            <div class="trend-big">{_pct_badge(ws.trends.message_volume_change_pct)}</div>
            <div class="trend-small">Messages vs Prior</div>
        </div>
    </div>
</div>

<!-- People & Channels -->
<div class="section">
    <div class="section-title">Leaderboards</div>
    <div class="cards">
        <div class="card">
            <h3>Top People</h3>
            {people_table}
        </div>
        <div class="card">
            <h3>Top Channels</h3>
            {channels_table}
        </div>
        <div class="card">
            <h3>Top Huddle Partners</h3>
            {huddle_table}
        </div>
    </div>
</div>

<!-- Mentions -->
<div class="section">
    <div class="section-title">Mentions</div>
    <div class="cards">
        <div class="card">
            <h3>Who Mentions You</h3>
            {mentioners_table}
        </div>
        <div class="card">
            <h3>Who You Mention</h3>
            {mentioned_table}
        </div>
    </div>
</div>

<!-- Daily Timeline -->
<div class="section">
    <div class="chart-wrap">
        <h3>Weekly Message Volume</h3>
        <canvas id="timeline" height="70"></canvas>
    </div>
</div>

<!-- Heatmap -->
<div class="section">
    <div class="chart-wrap">
        <h3>Activity Heatmap (Day × Hour)</h3>
        {heatmap_svg}
    </div>
</div>

<!-- Words & Emojis -->
<div class="section">
    <div class="cards">
        <div class="card">
            <h3>Your Top Words</h3>
            <div class="tags">{words_html or '<div class="empty-state">No data</div>'}</div>
        </div>
        <div class="card">
            <h3>Your Top Emojis</h3>
            <div class="tags">{emojis_html or '<div class="empty-state">No data</div>'}</div>
        </div>
    </div>
</div>

<!-- Quick Stats -->
<div class="section">
    <div class="section-title">Quick Stats</div>
    <div class="stats-row">
        <div class="stat-pill"><span class="val">{ws.messages.avg_words_per_message:.1f}</span> <span class="lbl">avg words/msg</span></div>
        <div class="stat-pill"><span class="val">{ws.messages.threads_started}</span> <span class="lbl">threads started</span></div>
        <div class="stat-pill"><span class="val">{ws.messages.links_shared}</span> <span class="lbl">links shared</span></div>
        <div class="stat-pill"><span class="val">{ws.messages.files_shared}</span> <span class="lbl">files shared</span></div>
    </div>
</div>

<!-- Bookends -->
<div class="section">
    <div class="section-title">Bookends</div>
    {_bookend("First Message", ws.messages.first_message)}
    {_bookend("Last Message", ws.messages.last_message)}
</div>

<!-- Footer -->
<div class="footer">
    SlackWrap v2 &middot; Generated {datetime.now().strftime("%b %d, %Y at %H:%M")} &middot; {sum(c for _, c in ws.messages.daily_volume_timeline):,} messages analyzed
</div>

<script>
const ctx = document.getElementById('timeline');
if (ctx) {{
    new Chart(ctx, {{
        type: 'bar',
        data: {{
            labels: {json.dumps(timeline_dates)},
            datasets: [{{
                data: {json.dumps(timeline_counts)},
                backgroundColor: 'rgba(99, 179, 237, 0.5)',
                borderColor: 'rgba(99, 179, 237, 0.9)',
                borderWidth: 1,
                borderRadius: 4,
                barPercentage: 0.85,
                categoryPercentage: 0.9,
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            animation: {{ duration: 0 }},
            plugins: {{ legend: {{ display: false }}, tooltip: {{
                backgroundColor: '#1a1a3e',
                titleColor: '#63b3ed',
                bodyColor: '#e2e2f0',
                borderColor: '#252550',
                borderWidth: 1,
                cornerRadius: 8,
                callbacks: {{ label: function(ctx) {{ return ctx.parsed.y + ' messages'; }} }}
            }} }},
            scales: {{
                x: {{ ticks: {{ color: '#7a7a9e', font: {{ size: 10 }}, maxRotation: 45 }}, grid: {{ display: false }} }},
                y: {{ ticks: {{ color: '#7a7a9e', font: {{ size: 11 }} }}, grid: {{ color: 'rgba(37,37,80,0.4)', drawBorder: false }} }}
            }}
        }}
    }});
}}
</script>
</body>
</html>'''
