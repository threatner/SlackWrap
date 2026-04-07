# SlackWrap

Your Slack year in review. A CLI tool that analyzes your Slack huddles and messages with a colleague — like Spotify Wrapped, but for your work conversations. Rich console output and an interactive HTML dashboard.

## Features

### Huddle Analytics
- Total huddle time, total huddle count
- Average, median, longest, and shortest huddle duration
- Frequency per week and per month
- Who initiates huddles (you vs. them, with percentages)
- Breakdown by day of week

### Message Analytics
- Total message volume with per-user split and percentages
- Messages per week, busiest single day
- Thread activity: top-level vs. thread messages, who starts threads
- Response time: median and average, measured turn-to-turn (skips gaps over 4 hours)
- Response time by hour: fastest and slowest hour of day
- Message style: average word count per user (code blocks and markup stripped)
- Most used words: top 10 per user
- Emojis in messages: total count and top 5 per user
- Reactions: given count and top reactions per user
- Links and files shared: count per user
- Conversation streaks: longest streak, current streak, longest silence (dead zone)
- First and last message with text preview

### Trend Analysis
- 30-day rolling comparison: last 30 days vs. previous 30 days
- Year-over-year: current month vs. same month last year, normalized to daily average to handle partial months fairly

### Combined Mode
- Side-by-side huddle and message stats in a single report
- Huddle-to-message ratio (messages per huddle)
- Unified day-of-week table with both huddle and message counts
- Most active hours (top 5)

### Output Formats
- Console: plain-text formatted output with section headers
- HTML: interactive single-file dashboard with Chart.js charts, dark theme, and emoji rendering via the gemoji CDN

## Setup

### 1. Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**
2. Choose **From scratch**, name it anything (e.g. "Huddle Analytics"), and select your workspace
3. Go to **OAuth & Permissions**
4. Under **User Token Scopes**, add all seven of the following:
   - `channels:history` — read messages from public channels
   - `groups:history` — read messages from private channels
   - `im:history` — read direct messages
   - `users:read` — look up user profiles
   - `channels:read` — list public channels
   - `groups:read` — list private channels
   - `im:read` — list DM conversations
5. Click **Install to Workspace** and authorize
6. Copy the **User OAuth Token** (it starts with `xoxp-`)

### 2. Configure

Create a `.env` file in the project root:

```
SLACK_USER_TOKEN=xoxp-your-token-here
```

Your Slack user ID is auto-detected from the token via `auth.test` — you do not need to provide it manually.

### 3. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Basic

```bash
python -m src.main
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--no-cache` | Skip reading and writing cache; fetch everything fresh |
| `--clear-cache` | Delete all cached data before running |

```bash
python -m src.main --no-cache
python -m src.main --clear-cache
```

### Interactive Flow

1. **Search** — enter a name or channel fragment
2. **Select** — pick from the matched results (DMs and channels)
3. **Shared channels** (DM only) — optionally include one or more shared channels to broaden the analysis
4. **Analytics type** — choose what to analyze:
   - `1` Huddle Time
   - `2` Message Analytics
   - `3` Both

The tool fetches messages (with incremental caching), computes stats, prints a console report, and saves an HTML report to the current directory.

## Analytics Reference

### Huddle Time

| Metric | Description |
|--------|-------------|
| Total time | Sum of all huddle durations |
| Total huddles | Number of completed huddles |
| Average / Median | Mean and median duration per huddle |
| Longest / Shortest | Single-huddle extremes |
| Who starts | Count and percentage of who created each huddle |
| By day of week | Huddle count per weekday |

### Messages

| Metric | Description |
|--------|-------------|
| Volume | Total messages, per-user split, per-week rate |
| Busiest day | Single calendar date with most messages |
| Thread activity | Top-level vs. in-thread messages, thread starters |
| Response time | Median and average turn-around, skipping gaps over 4 hours |
| Response time by hour | Hour with fastest/slowest median response |
| Message style | Average word count per user (strips code blocks, mentions, links, emoji) |
| Most used words | Top 10 words of 3+ letters per user |
| Emojis | In-text Slack emoji count and top 5 per user |
| Reactions | Reactions given and top 5 by name |
| Links & files | URL links and file uploads per user |
| Streaks | Longest consecutive-day streak, current streak, longest gap |
| First & last | Timestamps and text preview of first and last messages |

### Trends

| Metric | Description |
|--------|-------------|
| 30-day change | Messages in last 30 days vs. previous 30 days |
| Year-over-year | Current month vs. same month last year, compared as daily averages |

## Output

### Console

Plain-text output with section headers separated by dashes, printed to stdout.

### HTML Report

An auto-generated `slack_analytics_<Name>_<Context>.html` file is saved in the working directory and opened via a `file://` URL printed at the end. The file is self-contained and includes:

- Hero stat cards (total time, huddle count, message count, best streak)
- Chart.js bar and doughnut charts for hourly activity, day-of-week breakdown, monthly volume, and message split
- Detail cards for every analytics section
- Dark theme with emoji rendering via the `gemoji` image CDN (`:thumbsup:` renders as an image)

## Caching

On the first run for a given conversation, all messages are fetched from the Slack API and stored in `.cache/<channel_id>.json`. On subsequent runs, only messages newer than the last cached timestamp are fetched, then merged.

Cache files use version 2 format. Any cache file from an older format is automatically discarded and re-fetched.

Use `--no-cache` when you want a one-time fresh fetch without touching the cache. Use `--clear-cache` to wipe all cached conversations and start over.

## Rate Limiting

The Slack client tracks request counts per endpoint within a rolling 60-second window and applies per-tier limits:

| Tier | Limit used | Endpoints |
|------|-----------|-----------|
| Tier 2 | 18 req/min | `users.list`, `conversations.list` |
| Tier 3 | 45 req/min | `conversations.history`, `conversations.replies` |
| Tier 4 | 90 req/min | `users.info`, `conversations.members`, `auth.test` |

When the limit for a window is reached, the client calculates the exact remaining time until the oldest request in the window expires and sleeps only that long (burst-then-wait). If Slack returns a `429`, the `Retry-After` header is respected and the request is retried.

## Project Structure

```
huddle/
├── src/
│   ├── main.py               Entry point, CLI argument parsing, interactive flow, fetch orchestration
│   ├── slack_client.py       Slack API wrapper with tier-aware rate limiting and status display
│   ├── cache.py              JSON cache manager with versioning and incremental updates
│   ├── report.py             Huddle extraction, stats computation, console report formatter
│   ├── message_analytics.py  Message stats computation and console report formatter
│   ├── combined_report.py    Combined console report formatter (huddles + messages)
│   └── html_report.py        HTML dashboard generator with Chart.js charts
├── tests/
│   ├── test_cache.py
│   ├── test_main.py
│   ├── test_message_analytics.py
│   ├── test_report.py
│   └── test_slack_client.py
├── docs/
│   └── superpowers/          Design specs and implementation plans (project history)
├── requirements.txt
└── .env                      Not committed — add your SLACK_USER_TOKEN here
```

## Example Output

```
Slack Analytics
=======================================================
Channel:  Alex Johnson (DM)
Period:   2024-11-01 -> 2026-04-07 (522 days)

Huddle Time
-------------------------------------------------------
  Total time:       127h 14m (127.2 hours)
  Total huddles:    156
  Average:          49m per huddle (0.8 hrs)
  Median:           42m per huddle
  Longest:          3h 18m
  Shortest:         2m

Messages
-------------------------------------------------------
  Total messages:   4,821
  You:              2,344 (49%)
  Alex Johnson:     2,477 (51%)
  Per week:         63.4 messages
  Busiest day:      2025-03-14 (87 messages)

Trends
-------------------------------------------------------
  Last 30 days:     312 messages (+18.6% vs previous 30d)
  Apr 2026:         41 messages (+5.2% daily avg vs Apr 2025)

Thread Activity
-------------------------------------------------------
  Total messages:   4,821
  Top-level:        3,904 (81%)
  In threads:       917 (19%)
  Threads started:  You: 62 / Alex Johnson: 71

Who Starts Huddles
-------------------------------------------------------
  You:              89 (57%)
  Alex Johnson:     67 (43%)

Response Time (Messages)
-------------------------------------------------------
  You:              4m median, 9m avg
  Alex Johnson:     3m median, 7m avg

Message Style
-------------------------------------------------------
  You:              11.2 words avg
  Alex Johnson:     8.7 words avg

Most Used Words
-------------------------------------------------------
  You:              looks (142), review (98), think (87), sounds (76), good (71), ...
  Alex Johnson:     yeah (203), sounds (134), check (112), done (89), will (77), ...

Conversation Streaks
-------------------------------------------------------
  Longest streak:   47 days (Oct 7 - Nov 22)
  Current streak:   12 days
  Longest silence:  18 days (Aug 3 - Aug 21)

Frequency
-------------------------------------------------------
  Huddles/week:     2.1 (1h 43m)
  Messages/week:    63.4
  Per huddle:       ~31 messages exchanged

  HTML report: file:///Users/you/Projects/huddle/slack_analytics_Alex_Johnson_DM.html
```
