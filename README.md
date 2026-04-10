# SlackWrap

Your Slack year in review. A CLI tool that analyzes your Slack huddles and messages with a colleague — like Spotify Wrapped, but for your work conversations. Rich console output and an interactive HTML dashboard.

## Features

### Workspace Wrap (your full Slack year-in-review)
- Scans every DM, group DM, and channel you participate in
- Leaderboards: top conversations by message volume, top huddle partners by time
- Your stats: total messages sent, huddle hours, busiest day, top hours
- Mention graph: who mentions you the most, who you mention the most
- Monthly message volume trend chart
- Configurable time window (`--year`, `--from`/`--to`)
- Concurrent fetch with configurable workers (`--workers`)

### One-on-One Report (deep stats with one colleague)

#### Huddle Analytics
- Total huddle time, total huddle count
- Average, median, longest, and shortest huddle duration
- Frequency per week and per month
- Who initiates huddles (you vs. them, with percentages)
- Breakdown by day of week

#### Message Analytics
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

#### Trend Analysis
- 30-day rolling comparison: last 30 days vs. previous 30 days
- Year-over-year: current month vs. same month last year, normalized to daily average to handle partial months fairly

#### Combined Mode
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
4. Under **User Token Scopes**, add all of the following:
   - `channels:history` — read messages from public channels
   - `channels:read` — list public channels
   - `groups:history` — read messages from private channels
   - `groups:read` — list private channels
   - `im:history` — read direct messages
   - `im:read` — list DM conversations
   - `mpim:history` — read group DM messages
   - `mpim:read` — list group DMs
   - `users:read` — look up user profiles
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
| `--year YYYY` | Shorthand for `--from YYYY-01-01 --to YYYY-12-31` |
| `--from YYYY-MM-DD` | Window start date (inclusive) |
| `--to YYYY-MM-DD` | Window end date (inclusive) |
| `--fetch-only` | Fetch all in-scope conversations to `.cache/` and exit (no analytics) |
| `--workers N` | Concurrent fetch workers (default 4, max 8) |
| `--timezone TZ` | IANA timezone for day/hour stats (default: system local) |
| `--no-cache` | Skip reading and writing cache; fetch everything fresh |
| `--clear-cache` | Delete all cached data before running |

```bash
# Workspace wrap for 2026
python -m src.main --year 2026

# Custom date range
python -m src.main --from 2025-04-10 --to 2026-04-10

# Pre-fetch all data without running analytics
python -m src.main --fetch-only --year 2026

# One-off fresh fetch
python -m src.main --no-cache

# Clear cache and start over
python -m src.main --clear-cache
```

### Interactive Flow

When run without `--year` or `--from`/`--to`, the tool presents an interactive menu:

1. **Workspace wrap** — your full Slack year-in-review across all conversations
2. **One-on-one report** — deep stats with one colleague
   - Search for a name or channel
   - Pick from matched results (DMs and channels)
   - Optionally include shared channels
   - Choose analytics type: Huddle Time, Messages, or Both

The tool fetches messages (with incremental caching and concurrent workers), computes stats, prints a console report, and saves an HTML report to the current directory.

## Analytics Reference

### Workspace Wrap

| Section | Description |
|---------|-------------|
| Headline | Messages sent, huddle hours, humans reached, active conversations, longest streak, busiest day |
| Top People | Ranked by interaction score (DM volume + huddle time + thread co-participation) |
| Top Channels | Your most active channels by message count |
| Huddles | Total count/time, average, longest, partner leaderboard |
| Mentions | Times @mentioned, @mentions made, top mentioners, who you mention most |
| Trends | Message/huddle/people change vs. prior period, most/least active months |
| Top Words | Your most used words across all conversations |
| Bookends | First and last message with date and conversation |

### One-on-One: Huddle Time

| Metric | Description |
|--------|-------------|
| Total time | Sum of all huddle durations |
| Total huddles | Number of completed huddles |
| Average / Median | Mean and median duration per huddle |
| Longest / Shortest | Single-huddle extremes |
| Who starts | Count and percentage of who created each huddle |
| By day of week | Huddle count per weekday |

### One-on-One: Messages

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

### One-on-One: Trends

| Metric | Description |
|--------|-------------|
| 30-day change | Messages in last 30 days vs. previous 30 days |
| Year-over-year | Current month vs. same month last year, compared as daily averages |

## Output

### Console

Plain-text output with section headers separated by dashes, printed to stdout.

### HTML Report

An auto-generated HTML file is saved in the working directory and its `file://` URL is printed at the end. The file is self-contained and includes:

**Workspace wrap** (`slackwrap_<name>_<date_range>.html`):
- Hero stat cards (messages sent, huddle hours, people reached, streak)
- Monthly message volume chart (Chart.js)
- Top people and channel leaderboard cards
- Huddle partner leaderboard, mention graph, trends
- Dark neon dashboard theme

**One-on-one report** (`slack_analytics_<Name>_<Context>.html`):
- Hero stat cards (total time, huddle count, message count, best streak)
- Chart.js bar and doughnut charts for hourly activity, day-of-week breakdown, monthly volume, and message split
- Detail cards for every analytics section
- Dark theme with emoji rendering via the `gemoji` image CDN (`:thumbsup:` renders as an image)

## Caching

On the first run for a given conversation, all messages are fetched from the Slack API and stored in `.cache/<channel_id>.json`. On subsequent runs, only messages newer than the last cached timestamp are fetched, then merged. Workspace wrap also stores a discovery manifest at `.cache/_workspace_manifest.json` and a user directory at `.cache/_users.json`.

Cache files use version 2+ format. Any cache file from an older format is automatically discarded and re-fetched.

Use `--no-cache` when you want a one-time fresh fetch without touching the cache. Use `--clear-cache` to wipe all cached conversations and start over.

## Rate Limiting

The Slack client tracks request counts per endpoint within a rolling 60-second window and applies per-tier limits:

| Tier | Limit used | Endpoints |
|------|-----------|-----------|
| Tier 2 | 18 req/min | `users.list`, `conversations.list` |
| Tier 3 | 45 req/min | `conversations.history`, `conversations.replies` |
| Tier 4 | 90 req/min | `users.info`, `conversations.members`, `auth.test` |

When the limit for a window is reached, the client calculates the exact remaining time until the oldest request in the window expires and sleeps only that long (burst-then-wait). If Slack returns a `429`, the `Retry-After` header is respected and the request is retried. The rate limiter is thread-safe, supporting concurrent fetch workers (`--workers`).

## Privacy

SlackWrap stores data locally on your machine:

- **Cache** (`.cache/`): Message history is stored as plaintext JSON, including message text, user IDs, timestamps, and reactions. Use `--clear-cache` to delete all cached data.
- **HTML Reports**: Generated reports contain message excerpts (first/last messages), analytics, and colleague names. Be mindful when sharing reports.
- **Shared Channels**: When including shared channels, the cache stores all channel messages (not just between the two target users).

No data is sent to any external server. The only network calls are to the Slack API using your token.

## Project Structure

```
huddle/
├── src/
│   ├── main.py                  Entry point, CLI parsing, interactive menu
│   ├── slack_client.py          Slack API wrapper with tier-aware rate limiting
│   ├── cache.py                 JSON cache manager with versioning and incremental updates
│   ├── engine/
│   │   ├── models.py            Data models (User, Conversation, HuddleEvent, WorkspaceStats)
│   │   ├── conversation_stats.py  Per-conversation stats computation
│   │   ├── mentions.py          Mention extraction and counting
│   │   └── workspace_stats.py   Workspace-level aggregation (leaderboards, trends)
│   ├── orchestrators/
│   │   ├── person_flow.py       One-on-one report flow (search, select, analyze)
│   │   └── workspace_flow.py    Workspace fetch pipeline and wrap orchestrator
│   ├── reports/
│   │   ├── workspace_console.py Plain-text workspace report formatter
│   │   └── workspace_html.py    Workspace HTML dashboard generator
│   ├── report.py                Huddle stats computation and console formatter
│   ├── message_analytics.py     Message stats computation and console formatter
│   ├── combined_report.py       Combined console formatter (huddles + messages)
│   └── html_report.py           One-on-one HTML dashboard generator
├── tests/
│   ├── test_cache.py
│   ├── test_main.py
│   ├── test_slack_client.py
│   ├── test_report.py
│   ├── test_message_analytics.py
│   ├── test_engine_models.py
│   ├── test_engine_conversation_stats.py
│   ├── test_engine_mentions.py
│   ├── test_engine_workspace_stats.py
│   └── test_workspace_flow.py
├── requirements.txt
└── .env                         Not committed — add your SLACK_USER_TOKEN here
```

## Example Output

### Workspace Wrap

```
SlackWrap
============================================================
  Alex Johnson
  2026-01-01 → 2026-12-31 (365 days)

Headline
------------------------------------------------------------
  Messages sent:    12,847
  Huddle time:      214h 32m
  Humans reached:   43
  Active convos:    67
  Longest streak:   47 days (Oct 07 – Nov 22)
  Busiest day:      2026-03-14 (87 messages)

Top People (by interaction score)
------------------------------------------------------------
   1. Sarah Chen                 1,204 dm · 38h 12m huddle · 89 threads
   2. Mike Torres                892 dm · 22h 45m huddle · 64 threads
   3. Priya Patel                634 dm · 15h 08m huddle · 41 threads

Top Channels (your messages)
------------------------------------------------------------
   1. #engineering                 412 yours /  3,891 total
   2. #incidents                   287 yours /  1,456 total
   3. #design-reviews              198 yours /    923 total

Huddles
------------------------------------------------------------
  Total:            312 huddles, 214h 32m
  Average:          41m
  Longest:          3h 18m with Sarah Chen

Mentions
------------------------------------------------------------
  Times @mentioned: 847
  @mentions made:   623
  Top mentioners:
    Sarah Chen                 142 times
    Mike Torres                 98 times

Trends
------------------------------------------------------------
  Messages:         +18.6% vs prior period
  Huddle time:      +5.2% vs prior period
  People:           +4 vs prior period
  Most active:      Mar 2026 (1,847 msgs)
  Quietest:         Aug 2026 (412 msgs)
```

### One-on-One Report

```
Slack Analytics
=======================================================
Channel:  Sarah Chen (DM)
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
  Sarah Chen:       2,477 (51%)
  Per week:         63.4 messages
  Busiest day:      2025-03-14 (87 messages)

Trends
-------------------------------------------------------
  Last 30 days:     312 messages (+18.6% vs previous 30d)
  Apr 2026:         41 messages (+5.2% daily avg vs Apr 2025)

Conversation Streaks
-------------------------------------------------------
  Longest streak:   47 days (Oct 7 - Nov 22)
  Current streak:   12 days
  Longest silence:  18 days (Aug 3 - Aug 21)
```
