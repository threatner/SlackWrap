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

// Emoji shortcode to Unicode mapping
const emojiMap = {{
  'thumbsup':'\ud83d\udc4d','thumbsdown':'\ud83d\udc4e','+1':'\ud83d\udc4d','-1':'\ud83d\udc4e',
  'heart':'\u2764\ufe0f','fire':'\ud83d\udd25','eyes':'\ud83d\udc40','rocket':'\ud83d\ude80',
  'tada':'\ud83c\udf89','100':'\ud83d\udcaf','pray':'\ud83d\ude4f','clap':'\ud83d\udc4f',
  'smile':'\ud83d\ude04','laughing':'\ud83d\ude06','joy':'\ud83d\ude02','grinning':'\ud83d\ude00',
  'smiley':'\ud83d\ude03','wink':'\ud83d\ude09','blush':'\ud83d\ude0a','relaxed':'\u263a\ufe0f',
  'heart_eyes':'\ud83d\ude0d','kissing_heart':'\ud83d\ude18','stuck_out_tongue':'\ud83d\ude1b',
  'stuck_out_tongue_winking_eye':'\ud83d\ude1c','sunglasses':'\ud83d\ude0e','smirk':'\ud83d\ude0f',
  'unamused':'\ud83d\ude12','thinking_face':'\ud83e\udd14','raised_hands':'\ud83d\ude4c',
  'muscle':'\ud83d\udcaa','point_up':'\u261d\ufe0f','ok_hand':'\ud83d\udc4c','v':'\u270c\ufe0f',
  'wave':'\ud83d\udc4b','raised_hand':'\u270b','open_hands':'\ud83d\udc50',
  'star':'\u2b50','star2':'\ud83c\udf1f','sparkles':'\u2728','zap':'\u26a1',
  'sunny':'\u2600\ufe0f','cloud':'\u2601\ufe0f','snowflake':'\u2744\ufe0f',
  'checkmark':'\u2714\ufe0f','white_check_mark':'\u2705','heavy_check_mark':'\u2714\ufe0f',
  'x':'\u274c','warning':'\u26a0\ufe0f','no_entry':'\u26d4',
  'red_circle':'\ud83d\udd34','large_blue_circle':'\ud83d\udd35','green_circle':'\ud83d\udfe2',
  'bulb':'\ud83d\udca1','memo':'\ud83d\udcdd','pencil':'\u270f\ufe0f','pencil2':'\u270f\ufe0f',
  'mag':'\ud83d\udd0d','link':'\ud83d\udd17','paperclip':'\ud83d\udcce',
  'calendar':'\ud83d\udcc5','clock1':'\ud83d\udd50','hourglass':'\u231b',
  'phone':'\ud83d\udcf1','computer':'\ud83d\udcbb','keyboard':'\u2328\ufe0f',
  'email':'\ud83d\udce7','inbox_tray':'\ud83d\udce5','outbox_tray':'\ud83d\udce4',
  'speech_balloon':'\ud83d\udcac','thought_balloon':'\ud83d\udcad',
  'hammer':'\ud83d\udd28','wrench':'\ud83d\udd27','gear':'\u2699\ufe0f','package':'\ud83d\udce6',
  'trophy':'\ud83c\udfc6','medal':'\ud83c\udfc5','crown':'\ud83d\udc51',
  'gem':'\ud83d\udc8e','moneybag':'\ud83d\udcb0','dollar':'\ud83d\udcb5',
  'chart_with_upwards_trend':'\ud83d\udcc8','chart_with_downwards_trend':'\ud83d\udcc9',
  'bar_chart':'\ud83d\udcca',
  'lock':'\ud83d\udd12','unlock':'\ud83d\udd13','key':'\ud83d\udd11',
  'bell':'\ud83d\udd14','loudspeaker':'\ud83d\udce2','mega':'\ud83d\udce3',
  'rotating_light':'\ud83d\udea8','police_car':'\ud83d\ude93',
  'coffee':'\u2615','beer':'\ud83c\udf7a','pizza':'\ud83c\udf55','hamburger':'\ud83c\udf54',
  'dog':'\ud83d\udc36','cat':'\ud83d\udc31','monkey':'\ud83d\udc35',
  'see_no_evil':'\ud83d\ude48','hear_no_evil':'\ud83d\ude49','speak_no_evil':'\ud83d\ude4a',
  'ghost':'\ud83d\udc7b','skull':'\ud83d\udca0','alien':'\ud83d\udc7d','robot_face':'\ud83e\udd16',
  'poop':'\ud83d\udca9','hankey':'\ud83d\udca9',
  'confused':'\ud83d\ude15','worried':'\ud83d\ude1f','cry':'\ud83d\ude22','sob':'\ud83d\ude2d',
  'angry':'\ud83d\ude20','rage':'\ud83d\ude21','scream':'\ud83d\ude31','fearful':'\ud83d\ude28',
  'sweat':'\ud83d\ude13','sweat_smile':'\ud83d\ude05','relieved':'\ud83d\ude0c',
  'sleepy':'\ud83d\ude2a','sleeping':'\ud83d\ude34','dizzy_face':'\ud83d\ude35',
  'nerd_face':'\ud83e\udd13','face_with_monocle':'\ud83e\uddd0',
  'partying_face':'\ud83e\udd73','shushing_face':'\ud83e\udd2b',
  'hugging_face':'\ud83e\udd17','zipper_mouth_face':'\ud83e\udd10',
  'money_mouth_face':'\ud83e\udd11','exploding_head':'\ud83e\udd2f',
  'saluting_face':'\ud83e\udee1','handshake':'\ud83e\udd1d',
  'slightly_smiling_face':'\ud83d\ude42','upside_down_face':'\ud83d\ude43',
  'rolling_on_the_floor_laughing':'\ud83e\udd23','rofl':'\ud83e\udd23',
  'raised_eyebrow':'\ud83e\udd28','face_with_rolling_eyes':'\ud83d\ude44',
  'grimacing':'\ud83d\ude2c','lying_face':'\ud83e\udd25','shrug':'\ud83e\udd37',
  'facepalm':'\ud83e\udd26','man-shrugging':'\ud83e\udd37\u200d\u2642\ufe0f',
  'woman-shrugging':'\ud83e\udd37\u200d\u2640\ufe0f',
  'dart':'\ud83c\udfaf','bowling':'\ud83c\udfb3','video_game':'\ud83c\udfae',
  'headphones':'\ud83c\udfa7','guitar':'\ud83c\udfb8','trumpet':'\ud83c\udfba',
  'art':'\ud83c\udfa8','performing_arts':'\ud83c\udfad','microphone':'\ud83c\udfa4',
  'books':'\ud83d\udcda','book':'\ud83d\udcd6','bookmark':'\ud83d\udd16',
  'newspaper':'\ud83d\udcf0','scroll':'\ud83d\udcdc',
  'earth_americas':'\ud83c\udf0e','earth_asia':'\ud83c\udf0f','earth_africa':'\ud83c\udf0d',
  'rainbow':'\ud83c\udf08','ocean':'\ud83c\udf0a','mountain':'\u26f0\ufe0f',
  'camping':'\ud83c\udfd5\ufe0f','house':'\ud83c\udfe0','office':'\ud83c\udfe2',
  'airplane':'\u2708\ufe0f','car':'\ud83d\ude97','bus':'\ud83d\ude8c',
  'ship':'\ud83d\udea2','bike':'\ud83d\udeb2',
  'hourglass_flowing_sand':'\u23f3','stopwatch':'\u23f1\ufe0f','timer_clock':'\u23f2\ufe0f',
  'alarm_clock':'\u23f0',
  'pig':'\ud83d\udc37','chicken':'\ud83d\udc14','penguin':'\ud83d\udc27','butterfly':'\ud83e\udd8b',
  'bee':'\ud83d\udc1d','ladybug':'\ud83d\udc1e','turtle':'\ud83d\udc22','snake':'\ud83d\udc0d',
  'crab':'\ud83e\udd80','whale':'\ud83d\udc33','dolphin':'\ud83d\udc2c',
  'apple':'\ud83c\udf4e','banana':'\ud83c\udf4c','grapes':'\ud83c\udf47','watermelon':'\ud83c\udf49',
  'strawberry':'\ud83c\udf53','lemon':'\ud83c\udf4b','avocado':'\ud83e\udd51',
  'taco':'\ud83c\udf2e','burrito':'\ud83c\udf2f','popcorn':'\ud83c\udf7f',
  'cake':'\ud83c\udf82','cookie':'\ud83c\udf6a','chocolate_bar':'\ud83c\udf6b',
  'wine_glass':'\ud83c\udf77','cocktail':'\ud83c\udf78','tropical_drink':'\ud83c\udf79',
  'champagne':'\ud83c\udf7e',
  'balloon':'\ud83c\udf88','gift':'\ud83c\udf81','ribbon':'\ud83c\udf80',
  'confetti_ball':'\ud83c\udf8a','christmas_tree':'\ud83c\udf84','jack_o_lantern':'\ud83c\udf83',
  'flag-us':'\ud83c\uddfa\ud83c\uddf8','flag-in':'\ud83c\uddee\ud83c\uddf3',
}};
// Replace :shortcode: with emoji in all .value and .quote elements
document.addEventListener('DOMContentLoaded', () => {{
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
