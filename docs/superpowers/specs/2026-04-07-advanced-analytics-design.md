# Advanced Analytics Features — Design Spec

## Features

### 1. Cache v2 with New Fields

**New fields in `trim_message`:**
- `thread_ts` — parent thread timestamp (None for top-level messages)
- `reply_count` — number of replies (0 if not a thread parent)
- `files_count` — number of file attachments
- `file_types` — list of file type strings (e.g., ["png", "pdf"])

**Cache versioning:**
- Add `"version": 2` key to cache JSON root
- On `cache.load()`, if version is missing or < 2, delete the cache file and return None (triggers re-fetch)
- No migration — clean re-fetch is simpler and ensures all fields are populated

### 2. Thread Reply Fetching

**After `conversations.history` completes:**
1. Scan fetched messages for any with `reply_count > 0`
2. For each, call `conversations.replies(channel, ts)` to get all thread replies
3. Merge replies into the message list (they'll have `thread_ts` set to the parent's `ts`)
4. Store everything in cache — both top-level and thread messages

**API:** `conversations.replies` is Tier 3 (~50/min). Add to `ENDPOINT_TIERS` map.

**SlackClient changes:**
- Add `fetch_thread_replies(channel_id, thread_ts)` method
- Modify `fetch_messages` to accept `include_threads=False` parameter
- When `include_threads=True`, after fetching history, iterate threaded messages and fetch replies
- Progress display: "Fetching threads... (42/128, 1,230 replies)"

### 3. Trend Analysis

**Rolling 30-day comparison:**
- Count messages in last 30 days vs messages in days 31-60
- Compute percentage change
- Output: "Last 30 days: 342 messages (+18% vs previous 30 days)" or "(-12%)" if declining

**Year-over-year comparison:**
- Compare current calendar month to same month last year
- Output: "Apr 2026: 342 messages (+45% vs Apr 2025)" or "(no data for Apr 2025)"

**Stats keys:**
- `trend_last_30d_count`: int
- `trend_prev_30d_count`: int
- `trend_30d_pct_change`: float | None
- `trend_current_month`: str (e.g., "2026-04")
- `trend_current_month_count`: int
- `trend_yoy_month`: str (e.g., "2025-04")
- `trend_yoy_count`: int | None
- `trend_yoy_pct_change`: float | None

### 4. Huddle-to-Message Ratio

**Computed in combined report only** (needs both h_stats and m_stats).

- `huddle_to_message_ratio`: float — total_messages / total_huddles
- Output: "For every huddle, ~102 messages exchanged"
- Displayed in the Frequency section of combined report

### 5. Thread Breakdown

**Stats keys:**
- `total_messages`: int (already exists — now includes thread replies)
- `top_level_messages`: int (messages where thread_ts is None or equals own ts)
- `thread_messages`: int (messages where thread_ts differs from own ts)
- `thread_pct`: float
- `threads_started_by_you`: int
- `threads_started_by_them`: int

**Output:**
```
Thread Activity
--------------------------------------------------
  Total messages:   4,832
  Top-level:        3,200 (66%)
  In threads:       1,632 (34%)
  Threads started:  Rahul: 87 / John: 65
```

### 6. Response Time by Hour

**For each hour (0-23), compute median response time for turns where the response happened during that hour.**

- Reuse existing turn-based response time logic
- Group response times by the hour of the response message
- Only include hours with >= 3 data points (avoid noise from single responses)

**Stats keys:**
- `response_time_by_hour`: dict[int, int] — hour -> median response seconds

**Output (console):**
```
Response Time by Hour
--------------------------------------------------
  Fastest:          10:00 (2m median)
  Slowest:          17:00 (45m median)
```

**Output (HTML):** Bar chart showing median response time per hour.

### 7. Link & File Sharing

**Links:** Parse message text for `<https?://...>` patterns (Slack link format). Count per user.

**Files:** Count from `files_count` field in cached messages. Count per user.

**Stats keys:**
- `your_links_shared`: int
- `their_links_shared`: int
- `your_files_shared`: int
- `their_files_shared`: int

**Output:**
```
Links & Files
--------------------------------------------------
  Rahul:          89 links, 23 files
  John:           45 links, 12 files
```

## Files Changed

| File | Change |
|---|---|
| `src/cache.py` | Add version field, new trim fields, auto-clear on old version |
| `src/slack_client.py` | Add `fetch_thread_replies`, `conversations.replies` tier, `include_threads` param |
| `src/message_analytics.py` | Add all new stat computations + display sections |
| `src/combined_report.py` | Add huddle-to-message ratio, new sections |
| `src/html_report.py` | New cards + response-by-hour chart |
| `src/main.py` | Pass `include_threads=True` to fetch |
| `tests/test_message_analytics.py` | Tests for new stats |
| `tests/test_cache.py` | Test version detection + auto-clear |
