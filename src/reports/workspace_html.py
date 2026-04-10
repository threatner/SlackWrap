"""
Polished single-file HTML workspace wrap report.

render_workspace_html(ws: WorkspaceStats) -> str

Design: Spotify Wrapped meets neon data dashboard.
Dark canvas, vibrant accents, glass-morphism, scroll animations.
Self-contained: Google Fonts, Chart.js via CDN, inline CSS/JS.
"""
import json
import html as html_mod
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
        return '<span class="badge badge--neutral">—</span>'
    sign = "+" if val >= 0 else ""
    cls = "badge--up" if val >= 0 else "badge--down"
    return f'<span class="badge {cls}">{sign}{val:.1f}%</span>'


def _render_heatmap(data: dict[tuple[int, int], int]) -> str:
    if not data:
        return '<div class="empty">No activity data</div>'
    max_val = max(data.values()) if data else 1
    cell_w, cell_h, gap = 20, 20, 3
    label_w = 36
    header_h = 20
    w = label_w + 24 * (cell_w + gap)
    h = header_h + 7 * (cell_h + gap)

    svg = [f'<svg viewBox="0 0 {w} {h}" class="heatmap">']
    for hour in range(24):
        x = label_w + hour * (cell_w + gap) + cell_w // 2
        if hour % 3 == 0:
            svg.append(f'<text x="{x}" y="{header_h - 6}" text-anchor="middle" class="hm-label">{hour}h</text>')
    for dow in range(7):
        y = header_h + dow * (cell_h + gap)
        svg.append(f'<text x="0" y="{y + cell_h - 5}" class="hm-label">{DOW_NAMES[dow]}</text>')
        for hour in range(24):
            x = label_w + hour * (cell_w + gap)
            val = data.get((dow, hour), 0)
            intensity = val / max_val if max_val else 0
            # Color gradient: dark → cyan → green → yellow for intensity
            if intensity == 0:
                fill = "rgba(255,255,255,0.03)"
            elif intensity < 0.25:
                r, g, b = 30, 80, 120
            elif intensity < 0.5:
                r, g, b = 40, 160, 180
            elif intensity < 0.75:
                r, g, b = 80, 220, 160
            else:
                r, g, b = 160, 255, 100
            if intensity > 0:
                alpha = 0.3 + intensity * 0.7
                fill = f"rgba({r},{g},{b},{alpha:.2f})"
                svg.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" rx="4" fill="{fill}"><title>{DOW_NAMES[dow]} {hour}:00 — {val} msgs</title></rect>')
            else:
                svg.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" rx="4" fill="{fill}"><title>{DOW_NAMES[dow]} {hour}:00 — 0 msgs</title></rect>')
    svg.append('</svg>')
    return '\n'.join(svg)


def _leaderboard(items, columns, formatters):
    if not items:
        return '<div class="empty">No data yet</div>'
    rows = []
    for i, item in enumerate(items, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f'<span class="rank-num">{i}</span>'
        cells = [f'<td class="td-rank">{medal}</td>']
        for fmt in formatters:
            cells.append(f'<td>{fmt(item)}</td>')
        rows.append(f'<tr class="lb-row" style="animation-delay:{i*0.05}s">{"".join(cells)}</tr>')
    header = "".join(f'<th>{c}</th>' for c in [""] + columns)
    return f'<table class="lb"><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def render_workspace_html(ws: WorkspaceStats) -> str:
    start = ws.window_start.strftime("%b %d, %Y")
    end = ws.window_end.strftime("%b %d, %Y")
    days = (ws.window_end - ws.window_start).days
    me_name = _esc(ws.me.name)

    # Weekly chart data
    weekly: dict[str, int] = defaultdict(int)
    for d, c in ws.messages.daily_volume_timeline:
        week_start = d - timedelta(days=d.weekday())
        weekly[week_start.strftime("%b %d")] += c
    chart_labels = list(weekly.keys())
    chart_data = list(weekly.values())

    heatmap_svg = _render_heatmap(ws.messages.dow_hour_heatmap)

    # People leaderboard
    def _pname(p): return f'<span class="person">{_esc(p.user.name)}</span>'
    def _pscore(p):
        parts = []
        if p.dm_messages_exchanged: parts.append(f'<span class="pill pill--blue">{p.dm_messages_exchanged:,} DMs</span>')
        if p.huddle_seconds: parts.append(f'<span class="pill pill--purple">{_fmt_dur(p.huddle_seconds)}</span>')
        if p.thread_coparticipations: parts.append(f'<span class="pill pill--green">{p.thread_coparticipations} threads</span>')
        return " ".join(parts)

    people_html = _leaderboard(ws.people.top_by_interaction, ["Person", ""], [_pname, _pscore])
    channels_html = _leaderboard(
        ws.channels.top_by_my_messages, ["Channel", "Yours", "Total"],
        [lambda c: f'<span class="channel">#{_esc(c.name)}</span>',
         lambda c: f'<span class="num">{c.my_message_count:,}</span>',
         lambda c: f'<span class="num dim">{c.total_message_count:,}</span>'],
    )
    huddle_html = _leaderboard(
        ws.huddles.partner_leaderboard[:5], ["Partner", "Time"],
        [_pname, lambda p: f'<span class="num accent-warm">{_fmt_dur(p.huddle_seconds)}</span>'],
    )
    mentioners_html = _leaderboard(
        ws.mentions.top_mentioners_of_me[:5], ["Person", "Times"],
        [lambda mc: f'<span class="person">{_esc(mc.user.name)}</span>',
         lambda mc: f'<span class="num">{mc.count}</span>'],
    )
    mentioned_html = _leaderboard(
        ws.mentions.top_people_i_mentioned[:5], ["Person", "Times"],
        [lambda mc: f'<span class="person">{_esc(mc.user.name)}</span>',
         lambda mc: f'<span class="num">{mc.count}</span>'],
    )

    # Words + emojis
    words_html = " ".join(
        f'<span class="word-tag" style="font-size:{max(0.75, min(1.6, 0.75 + c/max(ws.messages.top_words[0][1],1)*0.85))}em">{_esc(w)} <b>{c}</b></span>'
        for w, c in ws.messages.top_words
    ) if ws.messages.top_words else '<div class="empty">—</div>'

    emojis_html = " ".join(
        f'<span class="emoji-tag">:{_esc(e)}: <b>{c}</b></span>'
        for e, c in ws.messages.top_emojis_in_text
    ) if ws.messages.top_emojis_in_text else '<div class="empty">—</div>'

    # Bookend helper
    def _bookend(icon, label, msg):
        if not msg: return ""
        dt = datetime.fromtimestamp(msg.ts, tz=timezone.utc).astimezone()
        return f'''<div class="bookend reveal">
            <div class="bookend__icon">{icon}</div>
            <div class="bookend__body">
                <div class="bookend__label">{label}</div>
                <div class="bookend__date">{dt.strftime("%b %d, %Y")} · {_esc(msg.conversation_name)}</div>
                <div class="bookend__text">"{_esc(msg.text_preview)}"</div>
            </div>
        </div>'''

    streak_val = f'{ws.hero.longest_streak.length_days} days' if ws.hero.longest_streak else "—"
    streak_sub = f'{ws.hero.longest_streak.start_date.strftime("%b %d")} – {ws.hero.longest_streak.end_date.strftime("%b %d")}' if ws.hero.longest_streak else ""
    busiest_val = str(ws.hero.busiest_day.message_count) if ws.hero.busiest_day else "—"
    busiest_sub = ws.hero.busiest_day.date.strftime("%b %d, %Y") if ws.hero.busiest_day else ""

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SlackWrap — {me_name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;800&family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
/* === RESET + BASE === */
*,*::before,*::after {{ margin:0;padding:0;box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ background:#08081a; color:#e8e8f0; font-family:'DM Sans',sans-serif; line-height:1.6; overflow-x:hidden; }}

/* === COLORS === */
:root {{
  --bg:#08081a; --surface:#10102a; --surface-solid:#10102a;
  --border:rgba(80,80,160,0.15); --glass:rgba(255,255,255,0.04);
  --text:#e8e8f0; --dim:#6e6e9a; --accent:#4fc3f7; --accent2:#ce93d8;
  --accent3:#ffb74d; --green:#66bb6a; --red:#ef5350; --pink:#f06292;
}}

/* noise overlay removed — SVG fractalNoise on fixed overlay kills scroll perf */

/* === HERO HEADER === */
.hero-header {{
  position:relative; padding:80px 24px 60px; text-align:center; overflow:hidden;
  background:
    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(79,195,247,0.12) 0%, transparent 60%),
    radial-gradient(ellipse 60% 40% at 80% 80%, rgba(206,147,216,0.08) 0%, transparent 50%),
    radial-gradient(ellipse 60% 40% at 20% 80%, rgba(255,183,77,0.06) 0%, transparent 50%);
}}
.hero-header h1 {{
  font-family:'Sora',sans-serif; font-weight:800; font-size:clamp(2.5em,6vw,4em);
  letter-spacing:-0.03em;
  background:linear-gradient(135deg, var(--accent) 0%, var(--accent2) 50%, var(--pink) 100%);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
}}
.hero-header .tagline {{
  font-size:1.15em; color:var(--dim); margin-top:8px; font-weight:400;
}}
.hero-header .period {{
  display:inline-block; margin-top:16px; padding:6px 20px; border-radius:100px;
  background:var(--glass); border:1px solid var(--border);
  font-family:'JetBrains Mono',monospace; font-size:0.85em; color:var(--accent); letter-spacing:0.5px;
}}

/* === STAT TILES === */
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:16px; padding:0 24px; max-width:1100px; margin:-32px auto 0; position:relative; z-index:2; }}
.tile {{
  background:var(--surface); /* no backdrop-filter — perf */
  border:1px solid var(--border); border-radius:16px; padding:24px 16px; text-align:center;
  transition:transform .25s,border-color .25s;
}}
.tile:hover {{ transform:translateY(-4px); border-color:rgba(79,195,247,0.3); }}
.tile__val {{
  font-family:'Sora',sans-serif; font-weight:800; font-size:2em; line-height:1.1;
  background:linear-gradient(180deg, #fff 0%, var(--accent) 100%);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
}}
.tile__label {{ font-size:0.72em; color:var(--dim); text-transform:uppercase; letter-spacing:1.5px; margin-top:6px; font-weight:600; }}
.tile__sub {{ font-size:0.7em; color:var(--dim); font-weight:400; display:block; margin-top:2px; }}

/* === SECTIONS === */
.section {{ max-width:1100px; margin:48px auto; padding:0 24px; }}
.section__title {{
  font-family:'Sora',sans-serif; font-weight:700; font-size:1.35em; letter-spacing:-0.01em;
  margin-bottom:20px; display:flex; align-items:center; gap:10px;
}}
.section__title::before {{
  content:''; display:inline-block; width:4px; height:22px; border-radius:2px;
  background:linear-gradient(180deg, var(--accent), var(--accent2));
}}

/* === CARDS === */
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }}
.card {{
  background:var(--surface); /* no backdrop-filter — perf */
  border:1px solid var(--border); border-radius:16px; padding:24px; overflow:hidden;
  position:relative;
}}
.card::before {{
  content:''; position:absolute; top:0; left:0; right:0; height:2px;
  background:linear-gradient(90deg, var(--accent), var(--accent2), var(--accent3));
  opacity:0.6; border-radius:16px 16px 0 0;
}}
.card h3 {{
  font-family:'Sora',sans-serif; font-size:0.82em; font-weight:600;
  text-transform:uppercase; letter-spacing:1px; color:var(--dim); margin-bottom:14px;
}}

/* === BANNER === */
.banner {{
  display:flex; gap:24px; justify-content:center; flex-wrap:wrap; padding:20px 28px;
  background:var(--surface); border:1px solid var(--border); border-radius:16px;
  /* no backdrop-filter — perf */
}}
.banner__item {{ text-align:center; min-width:100px; }}
.banner__val {{ font-family:'Sora',sans-serif; font-size:1.3em; font-weight:700; color:var(--accent); }}
.banner__label {{ font-size:0.7em; color:var(--dim); text-transform:uppercase; letter-spacing:0.5px; }}

/* === LEADERBOARD TABLE === */
.lb {{ width:100%; border-collapse:collapse; font-size:0.88em; }}
.lb thead th {{ text-align:left; color:var(--dim); font-size:0.7em; text-transform:uppercase; letter-spacing:0.8px; padding:6px 8px; border-bottom:1px solid var(--border); font-weight:500; }}
.lb-row {{ opacity:0; animation:fadeSlideIn .4s forwards; }}
@keyframes fadeSlideIn {{ from {{ opacity:0;transform:translateX(-8px); }} to {{ opacity:1;transform:none; }} }}
.lb td {{ padding:10px 8px; border-bottom:1px solid rgba(80,80,160,0.08); vertical-align:middle; }}
.td-rank {{ width:32px; font-size:1.1em; }}
.rank-num {{ color:var(--dim); font-family:'JetBrains Mono',monospace; font-size:0.85em; }}
.person {{ font-weight:600; color:var(--text); }}
.channel {{ font-weight:600; color:var(--accent3); }}
.num {{ font-family:'JetBrains Mono',monospace; font-weight:500; color:var(--accent); }}
.num.dim {{ color:var(--dim); }}
.num.accent-warm {{ color:var(--accent3); }}

/* === PILLS === */
.pill {{ display:inline-block; padding:2px 10px; border-radius:100px; font-size:0.78em; font-weight:600; font-family:'JetBrains Mono',monospace; }}
.pill--blue {{ background:rgba(79,195,247,0.12); color:var(--accent); }}
.pill--purple {{ background:rgba(206,147,216,0.12); color:var(--accent2); }}
.pill--green {{ background:rgba(102,187,106,0.12); color:var(--green); }}

.badge {{ display:inline-block; padding:3px 12px; border-radius:100px; font-size:0.82em; font-weight:700; font-family:'JetBrains Mono',monospace; }}
.badge--up {{ background:rgba(102,187,106,0.15); color:var(--green); }}
.badge--down {{ background:rgba(239,83,80,0.15); color:var(--red); }}
.badge--neutral {{ background:rgba(110,110,154,0.15); color:var(--dim); }}

/* === CHART WRAP === */
.chart-card {{
  background:var(--surface); border:1px solid var(--border); border-radius:16px;
  padding:24px; margin-bottom:16px; backdrop-filter:blur(16px); position:relative;
}}
.chart-card::before {{
  content:''; position:absolute; top:0; left:0; right:0; height:2px;
  background:linear-gradient(90deg, var(--green), var(--accent));
  opacity:0.5; border-radius:16px 16px 0 0;
}}
.chart-card h3 {{
  font-family:'Sora',sans-serif; font-size:0.82em; font-weight:600;
  text-transform:uppercase; letter-spacing:1px; color:var(--dim); margin-bottom:14px;
}}

/* === HEATMAP === */
.heatmap {{ width:100%; height:auto; }}
.hm-label {{ fill:var(--dim); font-size:9px; font-family:'JetBrains Mono',monospace; }}

/* === WORD TAGS === */
.word-cloud {{ display:flex; flex-wrap:wrap; gap:8px; align-items:baseline; }}
.word-tag {{
  display:inline-block; padding:4px 14px; border-radius:10px;
  background:rgba(79,195,247,0.08); border:1px solid rgba(79,195,247,0.15);
  color:var(--accent); font-weight:500; transition:transform .2s,background .2s;
}}
.word-tag:hover {{ transform:scale(1.08); background:rgba(79,195,247,0.15); }}
.word-tag b {{ color:#fff; margin-left:4px; font-family:'JetBrains Mono',monospace; font-size:0.85em; }}

.emoji-tags {{ display:flex; flex-wrap:wrap; gap:8px; }}
.emoji-tag {{
  display:inline-block; padding:6px 14px; border-radius:10px;
  background:rgba(255,183,77,0.08); border:1px solid rgba(255,183,77,0.15);
  color:var(--accent3); font-weight:500;
}}
.emoji-tag b {{ color:#fff; margin-left:4px; font-family:'JetBrains Mono',monospace; font-size:0.85em; }}

/* === STATS ROW === */
.stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; }}
.stat-card {{
  background:var(--glass); border:1px solid var(--border); border-radius:12px;
  padding:16px; text-align:center;
}}
.stat-card__val {{ font-family:'Sora',sans-serif; font-size:1.5em; font-weight:700; color:var(--accent); }}
.stat-card__label {{ font-size:0.72em; color:var(--dim); text-transform:uppercase; letter-spacing:0.8px; margin-top:4px; }}

/* === BOOKENDS === */
.bookend {{
  display:flex; gap:16px; align-items:flex-start;
  background:var(--surface); border:1px solid var(--border); border-radius:16px;
  padding:20px; margin-bottom:12px; backdrop-filter:blur(16px);
}}
.bookend__icon {{ font-size:1.8em; flex-shrink:0; }}
.bookend__label {{ font-size:0.7em; color:var(--accent2); text-transform:uppercase; letter-spacing:1.2px; font-weight:700; }}
.bookend__date {{ color:var(--accent); font-size:0.85em; margin-top:2px; font-family:'JetBrains Mono',monospace; }}
.bookend__text {{ color:var(--dim); font-style:italic; margin-top:4px; font-size:0.9em; }}

/* === FOOTER === */
.footer {{ text-align:center; padding:60px 24px; color:var(--dim); font-size:0.75em; }}
.footer a {{ color:var(--accent); text-decoration:none; }}

/* === EMPTY === */
.empty {{ color:var(--dim); font-style:italic; padding:8px 0; }}

/* === SCROLL REVEAL === */
.reveal {{ opacity:0; transform:translateY(20px); transition:opacity .6s ease, transform .6s ease; }}
.reveal.visible {{ opacity:1; transform:none; }}
</style>
</head>
<body>

<!-- HERO -->
<div class="hero-header">
  <h1>SlackWrap</h1>
  <div class="tagline">{me_name}'s Year on Slack</div>
  <div class="period">{start} → {end} · {days} days</div>
</div>

<!-- TILES -->
<div class="tiles">
  <div class="tile reveal">
    <div class="tile__val">{ws.hero.total_messages_sent:,}</div>
    <div class="tile__label">Messages Sent</div>
  </div>
  <div class="tile reveal">
    <div class="tile__val">{_fmt_dur(ws.hero.total_huddle_seconds)}</div>
    <div class="tile__label">Huddle Time</div>
  </div>
  <div class="tile reveal">
    <div class="tile__val">{ws.hero.unique_humans}</div>
    <div class="tile__label">Humans Reached</div>
  </div>
  <div class="tile reveal">
    <div class="tile__val">{ws.hero.active_conversations}</div>
    <div class="tile__label">Active Convos</div>
  </div>
  <div class="tile reveal">
    <div class="tile__val">{streak_val}</div>
    <div class="tile__label">Longest Streak</div>
    <span class="tile__sub">{streak_sub}</span>
  </div>
  <div class="tile reveal">
    <div class="tile__val">{busiest_val}</div>
    <div class="tile__label">Busiest Day</div>
    <span class="tile__sub">{busiest_sub}</span>
  </div>
</div>

<!-- BANNER -->
<div class="section">
  <div class="banner reveal">
    <div class="banner__item">
      <div class="banner__val">{ws.mentions.total_mentions_received:,}</div>
      <div class="banner__label">Times @mentioned</div>
    </div>
    <div class="banner__item">
      <div class="banner__val">{ws.mentions.total_mentions_made:,}</div>
      <div class="banner__label">@mentions Made</div>
    </div>
    <div class="banner__item">
      <div class="banner__val">{ws.huddles.total_huddles}</div>
      <div class="banner__label">Huddles</div>
    </div>
    <div class="banner__item">
      <div class="banner__val">{_pct_badge(ws.trends.message_volume_change_pct)}</div>
      <div class="banner__label">vs Prior Period</div>
    </div>
  </div>
</div>

<!-- LEADERBOARDS -->
<div class="section">
  <div class="section__title reveal">Leaderboards</div>
  <div class="cards">
    <div class="card reveal"><h3>Top People</h3>{people_html}</div>
    <div class="card reveal"><h3>Top Channels</h3>{channels_html}</div>
    <div class="card reveal"><h3>Huddle Partners</h3>{huddle_html}</div>
  </div>
</div>

<!-- MENTIONS -->
<div class="section">
  <div class="section__title reveal">Mentions</div>
  <div class="cards">
    <div class="card reveal"><h3>Who Mentions You</h3>{mentioners_html}</div>
    <div class="card reveal"><h3>Who You Mention</h3>{mentioned_html}</div>
  </div>
</div>

<!-- WEEKLY CHART -->
<div class="section">
  <div class="chart-card reveal">
    <h3>Weekly Message Volume</h3>
    <canvas id="weeklyChart" height="75"></canvas>
  </div>
</div>

<!-- HEATMAP -->
<div class="section">
  <div class="chart-card reveal">
    <h3>Activity Heatmap · Day × Hour</h3>
    {heatmap_svg}
  </div>
</div>

<!-- WORDS + EMOJI -->
<div class="section">
  <div class="cards">
    <div class="card reveal"><h3>Your Top Words</h3><div class="word-cloud">{words_html}</div></div>
    <div class="card reveal"><h3>Your Top Emojis</h3><div class="emoji-tags">{emojis_html}</div></div>
  </div>
</div>

<!-- QUICK STATS -->
<div class="section">
  <div class="section__title reveal">Quick Stats</div>
  <div class="stats-grid reveal">
    <div class="stat-card"><div class="stat-card__val">{ws.messages.avg_words_per_message:.1f}</div><div class="stat-card__label">Avg Words / Msg</div></div>
    <div class="stat-card"><div class="stat-card__val">{ws.messages.threads_started}</div><div class="stat-card__label">Threads Started</div></div>
    <div class="stat-card"><div class="stat-card__val">{ws.messages.links_shared}</div><div class="stat-card__label">Links Shared</div></div>
    <div class="stat-card"><div class="stat-card__val">{ws.messages.files_shared}</div><div class="stat-card__label">Files Shared</div></div>
    <div class="stat-card"><div class="stat-card__val">{ws.messages.threads_replied_in}</div><div class="stat-card__label">Threads Replied</div></div>
    <div class="stat-card"><div class="stat-card__val">{len(ws.channels.lurker_channels)}</div><div class="stat-card__label">Lurker Channels</div></div>
  </div>
</div>

<!-- BOOKENDS -->
<div class="section">
  <div class="section__title reveal">Bookends</div>
  {_bookend("🌅", "First Message", ws.messages.first_message)}
  {_bookend("🌙", "Last Message", ws.messages.last_message)}
</div>

<!-- FOOTER -->
<div class="footer">
  <p>SlackWrap v2 · Generated {datetime.now().strftime("%b %d, %Y at %H:%M")}</p>
  <p>{sum(c for _, c in ws.messages.daily_volume_timeline):,} messages analyzed across {ws.hero.active_conversations} conversations</p>
</div>

<script>
// Scroll reveal
const obs = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{ if(e.isIntersecting) {{ e.target.classList.add('visible'); obs.unobserve(e.target); }} }});
}}, {{ threshold:0.1 }});
document.querySelectorAll('.reveal').forEach(el => obs.observe(el));

// Weekly chart
const ctx = document.getElementById('weeklyChart');
if (ctx) {{
  const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 300);
  gradient.addColorStop(0, 'rgba(79, 195, 247, 0.4)');
  gradient.addColorStop(1, 'rgba(79, 195, 247, 0.02)');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {json.dumps(chart_labels)},
      datasets: [{{
        data: {json.dumps(chart_data)},
        backgroundColor: gradient,
        borderColor: 'rgba(79, 195, 247, 0.8)',
        borderWidth: 1.5,
        borderRadius: 6,
        barPercentage: 0.8,
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      animation: {{ duration:800, easing:'easeOutQuart' }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor:'#10102a', titleColor:'#4fc3f7', bodyColor:'#e8e8f0',
          borderColor:'rgba(80,80,160,0.3)', borderWidth:1, cornerRadius:10,
          padding:12, titleFont:{{ family:'Sora',weight:'600' }},
          callbacks:{{ label: ctx => ctx.parsed.y.toLocaleString() + ' messages' }}
        }}
      }},
      scales: {{
        x: {{ ticks:{{ color:'#6e6e9a',font:{{ family:'JetBrains Mono',size:10 }},maxRotation:45 }}, grid:{{ display:false }} }},
        y: {{ ticks:{{ color:'#6e6e9a',font:{{ family:'JetBrains Mono',size:10 }} }}, grid:{{ color:'rgba(80,80,160,0.1)',drawBorder:false }} }}
      }}
    }}
  }});
}}
</script>
</body>
</html>'''
