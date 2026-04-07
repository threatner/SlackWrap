# Huddle Time Tracker — Design Spec

## Purpose

A Python CLI tool that fetches Slack huddle history for a selected channel/DM and reports total time spent in huddles with a colleague. Provides per-huddle breakdown and aggregate statistics.

## Constraints

- No Slack workspace admin access
- Regular User OAuth Token (`xoxp-`) only
- Historical data only (no real-time event listener in v1)
- Per-user join/leave timestamps are not available from Slack's API — huddle duration is treated as shared time for all participants listed in `participant_history`

## Architecture

Single Python CLI application with three modules:

- **`main.py`** — Entry point. Handles interactive channel selection flow and orchestrates fetch + report.
- **`slack_client.py`** — Wraps Slack API calls. Handles pagination, rate limiting, and user/channel resolution.
- **`report.py`** — Computes statistics and formats CLI output.

## Data Flow

1. User launches the script
2. Script prompts: "Search for a person or channel:"
3. User types a name (e.g., "john")
4. Script searches users via `users.list` and channels via `conversations.list`, displays numbered matches
5. User selects from the list
6. Script calls `conversations.history` with pagination (max 200 per request) to fetch all messages from the selected channel
7. Filters for messages where `subtype == "huddle_thread"` and `room.has_ended == true`
8. Extracts from each huddle's `room` object: `date_start`, `date_end`, `participant_history`, `created_by`
9. Filters huddles where the user's own Slack ID appears in `participant_history`
10. Computes per-huddle duration (`date_end - date_start`) and aggregate statistics
11. Resolves user IDs to display names via `users.info` (cached)
12. Prints formatted report to terminal

## Interactive Channel Selection

On launch, the script:

1. Prompts for a search query
2. Searches users (`users.list`) for name matches and finds corresponding DM channels (`conversations.list` with `types=im`)
3. Searches channels (`conversations.list` with `types=public_channel,private_channel`) for name matches
4. Displays numbered results:
   ```
   Search: john

   1. John Smith (DM)
   2. John Doe (DM)
   3. #john-project (channel)

   Select [1-3]:
   ```
5. User picks a number, script proceeds with that channel ID

## Slack API Details

### Endpoints Used

| Endpoint | Purpose |
|---|---|
| `conversations.history` | Fetch messages including huddle_thread messages |
| `conversations.list` | List DMs, channels for selection |
| `users.list` | Search users by name |
| `users.info` | Resolve user ID to display name (cached) |

### Huddle Message Structure

Huddles appear as messages with `subtype: "huddle_thread"`. The `room` object contains:

- `date_start` — Unix timestamp, huddle start
- `date_end` — Unix timestamp, huddle end (`0` if ongoing)
- `has_ended` — Boolean
- `participant_history` — Flat array of user IDs who ever joined
- `created_by` — User ID of who started the huddle

### Rate Limiting

`conversations.history` is Tier 3 (~50 req/min). The script adds a small delay between paginated requests to stay within limits.

### Required OAuth Scopes (User Token)

| Scope | Purpose |
|---|---|
| `channels:history` | Read huddle messages from public channels |
| `groups:history` | Read from private channels |
| `im:history` | Read from DMs |
| `users:read` | Search and resolve user names |
| `channels:read` | List public channels |
| `groups:read` | List private channels |
| `im:read` | List DM conversations |

## CLI Report Format

```
Huddle Time Report
==================
Channel: DM with @colleague
Period:  2025-01-15 -> 2026-04-07
Total huddles: 47

Date         Started By    Duration
-------------------------------------
2025-01-15   You           0h 32m
2025-01-18   @colleague    1h 05m
2025-01-22   You           0h 15m
...

Summary
-------------------------------------
Total time:      38h 42m
Avg per huddle:  0h 49m
Longest huddle:  3h 12m
Shortest huddle: 0h 04m
```

- Dates in local timezone
- User IDs resolved to display names (cached)
- "You" shown for the user's own ID
- Summary stats: total, average, longest, shortest

## Project Structure

```
huddle/
├── .env                  # Token + user ID (gitignored)
├── .env.example          # Template showing required vars
├── .gitignore
├── requirements.txt      # requests, python-dotenv
├── README.md             # Setup guide (Slack app creation + usage)
└── src/
    ├── __init__.py
    ├── main.py           # Entry point, interactive flow
    ├── slack_client.py   # API calls, pagination, rate limiting
    └── report.py         # Stats computation + CLI formatting
```

## Configuration

Via `.env` file:

```
SLACK_USER_TOKEN=xoxp-...
SLACK_USER_ID=U12345...
```

First-run check: if `.env` is missing or token is invalid, the script prints a short guide on creating the Slack app and obtaining the token.

## Future Extensions (Out of Scope for v1)

- Group channel / group DM support
- Per-user overlap time tracking via real-time `user_huddle_changed` events
- Export to CSV/JSON
- Date range filtering
- Better analytics (weekly/monthly breakdowns, trends)
