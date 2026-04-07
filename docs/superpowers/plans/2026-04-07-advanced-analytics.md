# Advanced Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 new analytics features: trend analysis, huddle-to-message ratio, thread breakdown, response time by hour, and link/file sharing stats.

**Architecture:** Cache gets versioned (v2) with new fields (`thread_ts`, `reply_count`, `files_count`, `file_types`). Stale caches auto-clear on version mismatch. `SlackClient` gains thread reply fetching via `conversations.replies`. All new stat computations live in `compute_message_stats` in `message_analytics.py`. Huddle-to-message ratio is computed exclusively in `combined_report.py` since it needs both datasets. Display updates go into `format_message_report`, `format_combined_report`, and `generate_html_report`.

**Tech Stack:** Python 3.10+, requests, pytest

---

## File Map

| File | Change | Responsibility |
|---|---|---|
| `src/cache.py` | Modify | Add `CACHE_VERSION = 2`, new trim fields, version check in `load()`, version tag in `save()` |
| `src/slack_client.py` | Modify | Add `conversations.replies` to `ENDPOINT_TIERS`, add `fetch_thread_replies()`, add `include_threads` param to `fetch_messages()` |
| `src/message_analytics.py` | Modify | Add trend analysis, thread breakdown, response-time-by-hour, link/file sharing computations + display sections |
| `src/combined_report.py` | Modify | Add huddle-to-message ratio, thread breakdown section, trend section, response-by-hour section, links & files section |
| `src/html_report.py` | Modify | Add trend card, thread breakdown card, response-by-hour bar chart, links & files card |
| `src/main.py` | Modify | Pass `include_threads=True` to `fetch_messages` in `fetch_with_cache` |
| `tests/test_cache.py` | Modify | Add tests for version detection, auto-clear on old version, new trim fields |
| `tests/test_message_analytics.py` | Modify | Add tests for trend analysis, thread breakdown, response-by-hour, links & files |

---

### Task 1: Cache v2 — Versioning & New Fields

**Files:**
- Modify: `src/cache.py`
- Modify: `tests/test_cache.py`

- [ ] **Step 1: Write failing tests for cache v2**

Add these tests to the existing `TestCacheManager` class in `/Users/devx/Projects/huddle/tests/test_cache.py`:

```python
# Add at the top of the file, alongside existing imports
from src.cache import CacheManager, CACHE_VERSION


# Add these test methods inside class TestCacheManager:

    def test_save_includes_version(self):
        messages = [{"user": "U001", "ts": "1.0", "text": "hi", "subtype": None}]
        self.cm.save("D001", messages, last_ts="1.0")
        result = self.cm.load("D001")
        assert result is not None
        assert result["version"] == CACHE_VERSION

    def test_load_returns_none_for_missing_version(self):
        """Cache files without a version key should be auto-cleared."""
        path = os.path.join(self.tmpdir, "D001.json")
        data = {"channel_id": "D001", "last_ts": "1.0", "messages": []}
        with open(path, "w") as f:
            json.dump(data, f)
        result = self.cm.load("D001")
        assert result is None
        # File should have been deleted
        assert not os.path.exists(path)

    def test_load_returns_none_for_old_version(self):
        """Cache files with version < CACHE_VERSION should be auto-cleared."""
        path = os.path.join(self.tmpdir, "D001.json")
        data = {"channel_id": "D001", "last_ts": "1.0", "messages": [], "version": 1}
        with open(path, "w") as f:
            json.dump(data, f)
        result = self.cm.load("D001")
        assert result is None
        assert not os.path.exists(path)

    def test_load_accepts_current_version(self):
        messages = [{"user": "U001", "ts": "1.0", "text": "hi", "subtype": None}]
        self.cm.save("D001", messages, last_ts="1.0")
        result = self.cm.load("D001")
        assert result is not None
        assert result["version"] == CACHE_VERSION
        assert len(result["messages"]) == 1

    def test_trim_message_includes_thread_fields(self):
        msg = {
            "user": "U001", "ts": "1700000000.000000", "text": "reply",
            "subtype": None, "thread_ts": "1699999000.000000",
            "reply_count": 5,
            "files": [
                {"filetype": "png", "id": "F1"},
                {"filetype": "pdf", "id": "F2"},
            ],
        }
        trimmed = CacheManager.trim_message(msg)
        assert trimmed["thread_ts"] == "1699999000.000000"
        assert trimmed["reply_count"] == 5
        assert trimmed["files_count"] == 2
        assert trimmed["file_types"] == ["png", "pdf"]

    def test_trim_message_defaults_for_missing_thread_fields(self):
        msg = {"user": "U001", "ts": "1.0", "text": "hi", "subtype": None}
        trimmed = CacheManager.trim_message(msg)
        assert trimmed["thread_ts"] is None
        assert trimmed["reply_count"] == 0
        assert trimmed["files_count"] == 0
        assert trimmed["file_types"] == []

    def test_append_preserves_version(self):
        old = [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}]
        self.cm.save("D001", old, last_ts="1.0")
        new = [{"user": "U002", "ts": "2.0", "text": "b", "subtype": None}]
        self.cm.append("D001", new, last_ts="2.0")
        result = self.cm.load("D001")
        assert result is not None
        assert result["version"] == CACHE_VERSION
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_cache.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Add `CACHE_VERSION` constant and update `trim_message`**

In `/Users/devx/Projects/huddle/src/cache.py`, add the constant at module level (after imports, before the class):

```python
CACHE_VERSION = 2
```

Then update the `trim_message` static method to include the new fields. Replace the existing `trim_message` method with:

```python
    @staticmethod
    def trim_message(msg: dict) -> dict:
        trimmed = {
            "user": msg.get("user"),
            "ts": msg.get("ts"),
            "text": msg.get("text", ""),
            "subtype": msg.get("subtype"),
            "thread_ts": msg.get("thread_ts"),
            "reply_count": msg.get("reply_count", 0),
            "files_count": len(msg.get("files", [])),
            "file_types": [f.get("filetype", "") for f in msg.get("files", [])],
        }
        if msg.get("reactions"):
            trimmed["reactions"] = [
                {"name": r.get("name", ""), "users": r.get("users", []), "count": r.get("count", 0)}
                for r in msg["reactions"]
            ]
        if "room" in msg:
            room = msg["room"]
            trimmed["room"] = {
                "date_start": room.get("date_start"),
                "date_end": room.get("date_end"),
                "has_ended": room.get("has_ended"),
                "participant_history": room.get("participant_history", []),
                "created_by": room.get("created_by"),
            }
        return trimmed
```

- [ ] **Step 4: Update `save()` to include version**

In `/Users/devx/Projects/huddle/src/cache.py`, replace the existing `save` method with:

```python
    def save(self, channel_id: str, messages: list[dict], last_ts: str):
        os.makedirs(self.cache_dir, exist_ok=True)
        data = {
            "version": CACHE_VERSION,
            "channel_id": channel_id,
            "last_ts": last_ts,
            "messages": messages,
        }
        with open(self._path(channel_id), "w") as f:
            json.dump(data, f)
```

- [ ] **Step 5: Update `load()` to check version**

In `/Users/devx/Projects/huddle/src/cache.py`, replace the existing `load` method with:

```python
    def load(self, channel_id: str) -> dict | None:
        path = self._path(channel_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, KeyError):
            return None
        # Version check — stale caches are auto-cleared
        version = data.get("version", 0)
        if version < CACHE_VERSION:
            os.remove(path)
            return None
        return data
```

- [ ] **Step 6: Update `append()` to preserve version**

In `/Users/devx/Projects/huddle/src/cache.py`, replace the existing `append` method with:

```python
    def append(self, channel_id: str, new_messages: list[dict], last_ts: str):
        existing = self.load(channel_id)
        if existing is None:
            self.save(channel_id, new_messages, last_ts)
            return
        existing["messages"].extend(new_messages)
        existing["last_ts"] = last_ts
        existing["version"] = CACHE_VERSION
        with open(self._path(channel_id), "w") as f:
            json.dump(existing, f)
```

- [ ] **Step 7: Run tests, confirm all pass**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_cache.py -v
```

- [ ] **Step 8: Commit**

```bash
cd /Users/devx/Projects/huddle && git add src/cache.py tests/test_cache.py && git commit -m "feat(cache): add cache v2 with versioning and thread/file fields

Add CACHE_VERSION = 2 constant. trim_message now extracts thread_ts,
reply_count, files_count, and file_types. save() writes version to JSON.
load() auto-deletes stale caches with missing or old version numbers.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Thread Reply Fetching

**Files:**
- Modify: `src/slack_client.py`
- Modify: `src/main.py`
- Modify: `tests/test_cache.py` (optional, integration-level)

- [ ] **Step 1: Write failing tests for thread reply fetching**

Create `/Users/devx/Projects/huddle/tests/test_slack_client_threads.py`:

```python
# tests/test_slack_client_threads.py
from unittest.mock import patch, MagicMock
from src.slack_client import SlackClient, ENDPOINT_TIERS


class TestEndpointTiers:
    def test_conversations_replies_is_tier_3(self):
        assert "conversations.replies" in ENDPOINT_TIERS
        assert ENDPOINT_TIERS["conversations.replies"] == 3


class TestFetchThreadReplies:
    @patch("src.slack_client.requests.get")
    def test_fetch_thread_replies_returns_messages(self, mock_get):
        # Auth response
        auth_resp = MagicMock()
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"ok": True, "user_id": "U_ME", "user": "testuser", "team": "TestTeam"}

        # Replies response
        replies_resp = MagicMock()
        replies_resp.status_code = 200
        replies_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"user": "U001", "ts": "1700000000.000", "text": "parent", "thread_ts": "1700000000.000"},
                {"user": "U002", "ts": "1700000060.000", "text": "reply 1", "thread_ts": "1700000000.000"},
                {"user": "U001", "ts": "1700000120.000", "text": "reply 2", "thread_ts": "1700000000.000"},
            ],
            "has_more": False,
        }

        mock_get.side_effect = [auth_resp, replies_resp]
        client = SlackClient(token="xoxp-test")
        replies = client.fetch_thread_replies("C001", "1700000000.000")
        assert len(replies) == 3
        assert replies[1]["text"] == "reply 1"

    @patch("src.slack_client.requests.get")
    def test_fetch_thread_replies_paginates(self, mock_get):
        auth_resp = MagicMock()
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"ok": True, "user_id": "U_ME", "user": "testuser", "team": "TestTeam"}

        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"user": "U001", "ts": "1.0", "text": "parent", "thread_ts": "1.0"},
            ],
            "has_more": True,
            "response_metadata": {"next_cursor": "cursor123"},
        }
        page2_resp = MagicMock()
        page2_resp.status_code = 200
        page2_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"user": "U002", "ts": "2.0", "text": "reply", "thread_ts": "1.0"},
            ],
            "has_more": False,
        }

        mock_get.side_effect = [auth_resp, page1_resp, page2_resp]
        client = SlackClient(token="xoxp-test")
        replies = client.fetch_thread_replies("C001", "1.0")
        assert len(replies) == 2


class TestFetchMessagesWithThreads:
    @patch("src.slack_client.requests.get")
    def test_include_threads_fetches_replies(self, mock_get):
        auth_resp = MagicMock()
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"ok": True, "user_id": "U_ME", "user": "testuser", "team": "TestTeam"}

        # History response — one message has reply_count > 0
        history_resp = MagicMock()
        history_resp.status_code = 200
        history_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"user": "U001", "ts": "1.0", "text": "threaded msg", "reply_count": 2, "thread_ts": "1.0"},
                {"user": "U002", "ts": "2.0", "text": "standalone"},
            ],
            "has_more": False,
        }

        # Replies response for the threaded message
        replies_resp = MagicMock()
        replies_resp.status_code = 200
        replies_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"user": "U001", "ts": "1.0", "text": "threaded msg", "thread_ts": "1.0"},
                {"user": "U003", "ts": "1.5", "text": "reply a", "thread_ts": "1.0"},
                {"user": "U001", "ts": "1.7", "text": "reply b", "thread_ts": "1.0"},
            ],
            "has_more": False,
        }

        mock_get.side_effect = [auth_resp, history_resp, replies_resp]
        client = SlackClient(token="xoxp-test")
        messages = client.fetch_messages("C001", include_threads=True)
        # Should have: standalone (ts=2.0) + parent (ts=1.0) + reply a (ts=1.5) + reply b (ts=1.7) = 4
        # The parent is already in history, replies include parent again — dedup by ts
        ts_set = {m["ts"] for m in messages}
        assert "1.0" in ts_set
        assert "1.5" in ts_set
        assert "1.7" in ts_set
        assert "2.0" in ts_set
        assert len(messages) == 4

    @patch("src.slack_client.requests.get")
    def test_include_threads_false_skips_replies(self, mock_get):
        auth_resp = MagicMock()
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"ok": True, "user_id": "U_ME", "user": "testuser", "team": "TestTeam"}

        history_resp = MagicMock()
        history_resp.status_code = 200
        history_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"user": "U001", "ts": "1.0", "text": "threaded msg", "reply_count": 2},
                {"user": "U002", "ts": "2.0", "text": "standalone"},
            ],
            "has_more": False,
        }

        mock_get.side_effect = [auth_resp, history_resp]
        client = SlackClient(token="xoxp-test")
        messages = client.fetch_messages("C001", include_threads=False)
        assert len(messages) == 2
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_slack_client_threads.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Add `conversations.replies` to `ENDPOINT_TIERS`**

In `/Users/devx/Projects/huddle/src/slack_client.py`, add to the `ENDPOINT_TIERS` dict:

```python
ENDPOINT_TIERS = {
    "users.list": 2,
    "users.info": 4,
    "conversations.list": 2,
    "conversations.history": 3,
    "conversations.replies": 3,
    "conversations.members": 4,
    "auth.test": 4,
}
```

- [ ] **Step 4: Add `fetch_thread_replies` method to `SlackClient`**

In `/Users/devx/Projects/huddle/src/slack_client.py`, add this method to the `SlackClient` class, after `fetch_messages`:

```python
    def fetch_thread_replies(self, channel_id: str, thread_ts: str) -> list[dict]:
        """Fetch all replies in a thread, including the parent message."""
        messages = []
        cursor = ""
        while True:
            params = {"channel": channel_id, "ts": thread_ts, "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.replies", params)
            messages.extend(data.get("messages", []))
            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return messages
```

- [ ] **Step 5: Add `include_threads` parameter to `fetch_messages`**

In `/Users/devx/Projects/huddle/src/slack_client.py`, update the `fetch_messages` method signature and body. Replace the existing method with:

```python
    def fetch_messages(self, channel_id: str, oldest: str | None = None, include_threads: bool = False) -> list[dict]:
        messages = []
        cursor = ""
        page = 0
        while True:
            page += 1
            _print_status(f"Fetching messages... (page {page}, {len(messages):,} fetched)")
            params = {"channel": channel_id, "limit": 999}
            if oldest:
                params["oldest"] = oldest
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.history", params)
            messages.extend(data.get("messages", []))
            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        _clear_status()

        if include_threads:
            threaded = [m for m in messages if m.get("reply_count", 0) > 0]
            total_threads = len(threaded)
            all_replies = []
            existing_ts = {m["ts"] for m in messages}
            for i, m in enumerate(threaded):
                _print_status(f"Fetching threads... ({i + 1}/{total_threads}, {len(all_replies):,} replies)")
                replies = self.fetch_thread_replies(channel_id, m["ts"])
                for reply in replies:
                    if reply["ts"] not in existing_ts:
                        all_replies.append(reply)
                        existing_ts.add(reply["ts"])
            _clear_status()
            messages.extend(all_replies)

        return messages
```

- [ ] **Step 6: Update `fetch_with_cache` in `main.py` to pass `include_threads=True`**

In `/Users/devx/Projects/huddle/src/main.py`, update the `fetch_with_cache` function. Change the two calls to `client.fetch_messages` to pass `include_threads=True`:

Replace:
```python
        raw = client.fetch_messages(channel_id)
```
with:
```python
        raw = client.fetch_messages(channel_id, include_threads=True)
```

There are two occurrences — one in the `not use_cache` branch and one in the `else` (no cache) branch.

Also update the incremental fetch call. Replace:
```python
        new_raw = client.fetch_messages(channel_id, oldest=last_ts)
```
with:
```python
        new_raw = client.fetch_messages(channel_id, oldest=last_ts, include_threads=True)
```

- [ ] **Step 7: Run tests, confirm all pass**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_slack_client_threads.py tests/test_cache.py -v
```

- [ ] **Step 8: Commit**

```bash
cd /Users/devx/Projects/huddle && git add src/slack_client.py src/main.py tests/test_slack_client_threads.py && git commit -m "feat(slack): add thread reply fetching via conversations.replies

Add fetch_thread_replies() method and include_threads parameter to
fetch_messages(). After fetching history, threaded messages (reply_count > 0)
have their replies fetched and merged with deduplication. main.py now
passes include_threads=True for all fetches.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Trend Analysis

**Files:**
- Modify: `src/message_analytics.py`
- Modify: `src/combined_report.py`
- Modify: `src/html_report.py`
- Modify: `tests/test_message_analytics.py`

- [ ] **Step 1: Write failing tests for trend analysis**

Add to `/Users/devx/Projects/huddle/tests/test_message_analytics.py`:

```python
from datetime import datetime, timezone, timedelta


def _make_messages_for_trends():
    """Generate messages spanning 70 days for trend testing.

    Layout:
    - Days 0-29 (most recent 30 days): 5 messages/day = 150
    - Days 30-59 (previous 30 days): 3 messages/day = 90
    - Days 60-69 (older): 1 message/day = 10
    Total: 250 messages
    """
    now = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
    messages = []
    msg_id = 0
    for day_offset in range(70):
        dt = now - timedelta(days=day_offset)
        if day_offset < 30:
            count = 5
        elif day_offset < 60:
            count = 3
        else:
            count = 1
        for i in range(count):
            ts = dt.timestamp() + i * 60
            messages.append({
                "user": "U_ME" if msg_id % 2 == 0 else "U001",
                "ts": str(ts),
                "text": f"message {msg_id}",
                "subtype": None,
            })
            msg_id += 1
    return messages


def _make_messages_for_yoy():
    """Generate messages for current month and same month last year."""
    messages = []
    msg_id = 0
    # April 2026: 20 messages
    for day in range(1, 21):
        dt = datetime(2026, 4, day, 10, 0, 0, tzinfo=timezone.utc)
        messages.append({
            "user": "U_ME" if msg_id % 2 == 0 else "U001",
            "ts": str(dt.timestamp()),
            "text": f"msg {msg_id}",
            "subtype": None,
        })
        msg_id += 1
    # April 2025: 10 messages
    for day in range(1, 11):
        dt = datetime(2025, 4, day, 10, 0, 0, tzinfo=timezone.utc)
        messages.append({
            "user": "U_ME" if msg_id % 2 == 0 else "U001",
            "ts": str(dt.timestamp()),
            "text": f"msg {msg_id}",
            "subtype": None,
        })
        msg_id += 1
    return messages


class TestTrendAnalysis:
    def test_30d_rolling_counts(self):
        messages = _make_messages_for_trends()
        stats = compute_message_stats(messages, "U_ME")
        assert stats["trend_last_30d_count"] == 150
        assert stats["trend_prev_30d_count"] == 90

    def test_30d_pct_change(self):
        messages = _make_messages_for_trends()
        stats = compute_message_stats(messages, "U_ME")
        # (150 - 90) / 90 * 100 = 66.7%
        assert stats["trend_30d_pct_change"] is not None
        assert abs(stats["trend_30d_pct_change"] - 66.7) < 0.1

    def test_30d_pct_change_none_when_prev_zero(self):
        """If there are no messages in the previous 30d, pct_change should be None."""
        now = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
        messages = []
        for i in range(10):
            ts = (now - timedelta(days=i)).timestamp()
            messages.append({"user": "U_ME", "ts": str(ts), "text": "hi", "subtype": None})
        stats = compute_message_stats(messages, "U_ME")
        assert stats["trend_last_30d_count"] == 10
        assert stats["trend_prev_30d_count"] == 0
        assert stats["trend_30d_pct_change"] is None

    def test_yoy_comparison(self):
        messages = _make_messages_for_yoy()
        stats = compute_message_stats(messages, "U_ME")
        assert stats["trend_current_month_count"] == 20
        assert stats["trend_yoy_count"] == 10
        # (20 - 10) / 10 * 100 = 100%
        assert stats["trend_yoy_pct_change"] is not None
        assert abs(stats["trend_yoy_pct_change"] - 100.0) < 0.1

    def test_yoy_none_when_no_prior_year_data(self):
        now = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
        messages = [
            {"user": "U_ME", "ts": str(now.timestamp()), "text": "hi", "subtype": None},
        ]
        stats = compute_message_stats(messages, "U_ME")
        assert stats["trend_yoy_count"] is None
        assert stats["trend_yoy_pct_change"] is None

    def test_trend_keys_present_in_empty_stats(self):
        stats = compute_message_stats([], "U_ME")
        assert stats["trend_last_30d_count"] == 0
        assert stats["trend_prev_30d_count"] == 0
        assert stats["trend_30d_pct_change"] is None
        assert stats["trend_current_month"] is not None
        assert stats["trend_current_month_count"] == 0
        assert stats["trend_yoy_count"] is None
        assert stats["trend_yoy_pct_change"] is None


class TestTrendDisplay:
    def test_format_message_report_includes_trends(self):
        messages = _make_messages_for_trends()
        stats = compute_message_stats(messages, "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "Trends" in output
        assert "Last 30 days:" in output
        assert "vs previous 30 days" in output

    def test_format_combined_report_includes_trends(self):
        from src.combined_report import format_combined_report
        messages = _make_messages_for_trends()
        m_stats = compute_message_stats(messages, "U_ME")
        h_stats = {
            "total_huddles": 0, "total_seconds": 0, "avg_seconds": 0,
            "longest_seconds": 0, "shortest_seconds": 0, "median_seconds": 0,
            "huddles": [], "started_by_you": 0, "started_by_them": 0,
            "monthly_breakdown": {}, "weekday_breakdown": {},
        }
        output = format_combined_report(h_stats, m_stats, "DM with Alice")
        assert "Trends" in output
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_message_analytics.py::TestTrendAnalysis tests/test_message_analytics.py::TestTrendDisplay -v 2>&1 | tail -20
```

- [ ] **Step 3: Add trend computation to `compute_message_stats`**

In `/Users/devx/Projects/huddle/src/message_analytics.py`, add this import at the top (alongside existing imports):

```python
from datetime import date, datetime, timedelta, timezone  # already present — no change needed
```

Add the following computation block inside `compute_message_stats`, after the existing `your_top_text_emojis` / `their_top_text_emojis` lines and before the final `return {` statement:

```python
    # --- Trend Analysis ---
    now = datetime.now(tz=timezone.utc).astimezone()
    today = now.date()
    thirty_days_ago = today - timedelta(days=30)
    sixty_days_ago = today - timedelta(days=60)

    trend_last_30d_count = 0
    trend_prev_30d_count = 0
    for m in sorted_msgs:
        msg_date = datetime.fromtimestamp(float(m["ts"]), tz=timezone.utc).astimezone().date()
        if msg_date > thirty_days_ago:
            trend_last_30d_count += 1
        elif msg_date > sixty_days_ago:
            trend_prev_30d_count += 1

    if trend_prev_30d_count > 0:
        trend_30d_pct_change = round((trend_last_30d_count - trend_prev_30d_count) / trend_prev_30d_count * 100, 1)
    else:
        trend_30d_pct_change = None

    # Year-over-year: current calendar month vs same month last year
    current_month_str = now.strftime("%Y-%m")
    yoy_month_str = f"{now.year - 1}-{now.strftime('%m')}"
    trend_current_month_count = 0
    trend_yoy_count_val = 0
    has_yoy_data = False
    for m in sorted_msgs:
        msg_month = datetime.fromtimestamp(float(m["ts"]), tz=timezone.utc).astimezone().strftime("%Y-%m")
        if msg_month == current_month_str:
            trend_current_month_count += 1
        elif msg_month == yoy_month_str:
            trend_yoy_count_val += 1
            has_yoy_data = True

    trend_yoy_count = trend_yoy_count_val if has_yoy_data else None
    if has_yoy_data and trend_yoy_count_val > 0:
        trend_yoy_pct_change = round((trend_current_month_count - trend_yoy_count_val) / trend_yoy_count_val * 100, 1)
    else:
        trend_yoy_pct_change = None
```

Add these keys to the empty-stats return dict (the `if not user_msgs: return {...}` block near the top):

```python
            "trend_last_30d_count": 0,
            "trend_prev_30d_count": 0,
            "trend_30d_pct_change": None,
            "trend_current_month": datetime.now(tz=timezone.utc).astimezone().strftime("%Y-%m"),
            "trend_current_month_count": 0,
            "trend_yoy_month": f"{datetime.now(tz=timezone.utc).astimezone().year - 1}-{datetime.now(tz=timezone.utc).astimezone().strftime('%m')}",
            "trend_yoy_count": None,
            "trend_yoy_pct_change": None,
```

Add these keys to the main return dict at the bottom:

```python
        "trend_last_30d_count": trend_last_30d_count,
        "trend_prev_30d_count": trend_prev_30d_count,
        "trend_30d_pct_change": trend_30d_pct_change,
        "trend_current_month": current_month_str,
        "trend_current_month_count": trend_current_month_count,
        "trend_yoy_month": yoy_month_str,
        "trend_yoy_count": trend_yoy_count,
        "trend_yoy_pct_change": trend_yoy_pct_change,
```

- [ ] **Step 4: Add trend display to `format_message_report`**

In `/Users/devx/Projects/huddle/src/message_analytics.py`, add a new section to `format_message_report`. Insert this block after the "Volume" section (after the `lines.append(f"  Per week:  ...")` block) and before the "Who Initiates" section:

```python
    # Trends
    has_trends = stats.get("trend_last_30d_count", 0) > 0 or stats.get("trend_prev_30d_count", 0) > 0
    if has_trends:
        lines.append("")
        lines.append("Trends")
        lines.append("-" * 50)
        pct_30d = stats.get("trend_30d_pct_change")
        pct_str = f" ({pct_30d:+.0f}% vs previous 30 days)" if pct_30d is not None else ""
        lines.append(f"  Last 30 days:     {stats['trend_last_30d_count']:,} messages{pct_str}")
        yoy_pct = stats.get("trend_yoy_pct_change")
        yoy_count = stats.get("trend_yoy_count")
        if yoy_count is not None:
            yoy_pct_str = f" ({yoy_pct:+.0f}% vs {stats['trend_yoy_month']})" if yoy_pct is not None else ""
            lines.append(f"  {stats['trend_current_month']}:        {stats['trend_current_month_count']:,} messages{yoy_pct_str}")
        else:
            lines.append(f"  {stats['trend_current_month']}:        {stats['trend_current_month_count']:,} messages (no data for {stats['trend_yoy_month']})")
```

- [ ] **Step 5: Add trend display to `format_combined_report`**

In `/Users/devx/Projects/huddle/src/combined_report.py`, add a trends section. Insert after the "Messages" section and before the "Who Initiates" section:

```python
    # --- Trends ---
    if has_messages:
        has_trends = m_stats.get("trend_last_30d_count", 0) > 0 or m_stats.get("trend_prev_30d_count", 0) > 0
        if has_trends:
            lines.append("Trends")
            lines.append("-" * 55)
            pct_30d = m_stats.get("trend_30d_pct_change")
            pct_str = f" ({pct_30d:+.0f}% vs previous 30 days)" if pct_30d is not None else ""
            lines.append(f"  Last 30 days:     {m_stats['trend_last_30d_count']:,} messages{pct_str}")
            yoy_pct = m_stats.get("trend_yoy_pct_change")
            yoy_count = m_stats.get("trend_yoy_count")
            if yoy_count is not None:
                yoy_pct_str = f" ({yoy_pct:+.0f}% vs {m_stats['trend_yoy_month']})" if yoy_pct is not None else ""
                lines.append(f"  {m_stats['trend_current_month']}:        {m_stats['trend_current_month_count']:,} messages{yoy_pct_str}")
            else:
                lines.append(f"  {m_stats['trend_current_month']}:        {m_stats['trend_current_month_count']:,} messages (no data for {m_stats['trend_yoy_month']})")
            lines.append("")
```

- [ ] **Step 6: Add trend card to HTML report**

In `/Users/devx/Projects/huddle/src/html_report.py`, add a trend card in the `generate_html_report` function, after the existing hero stats section and before the "Who Initiates" card. Add this inside the card-building section:

```python
    # Trend card
    if has_messages:
        has_trends = m_stats.get("trend_last_30d_count", 0) > 0 or m_stats.get("trend_prev_30d_count", 0) > 0
        if has_trends:
            trend_html = ""
            pct_30d = m_stats.get("trend_30d_pct_change")
            pct_str = f'({pct_30d:+.0f}%)' if pct_30d is not None else ""
            trend_html += f'<div class="stat-row"><span class="label">Last 30 days</span><span class="value">{m_stats["trend_last_30d_count"]:,} messages <small>{pct_str}</small></span></div>'
            pct_str_prev = ""
            trend_html += f'<div class="stat-row"><span class="label">Previous 30 days</span><span class="value">{m_stats["trend_prev_30d_count"]:,} messages</span></div>'
            yoy_count = m_stats.get("trend_yoy_count")
            yoy_pct = m_stats.get("trend_yoy_pct_change")
            if yoy_count is not None:
                yoy_pct_str = f'({yoy_pct:+.0f}%)' if yoy_pct is not None else ""
                trend_html += f'<div class="stat-row"><span class="label">{m_stats["trend_current_month"]}</span><span class="value">{m_stats["trend_current_month_count"]:,} <small>{yoy_pct_str} vs {m_stats["trend_yoy_month"]}</small></span></div>'
            else:
                trend_html += f'<div class="stat-row"><span class="label">{m_stats["trend_current_month"]}</span><span class="value">{m_stats["trend_current_month_count"]:,} <small>no prior year data</small></span></div>'
            cards.append(_card("Trends", trend_html))
```

- [ ] **Step 7: Run all tests, confirm they pass**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_message_analytics.py tests/test_cache.py -v
```

- [ ] **Step 8: Commit**

```bash
cd /Users/devx/Projects/huddle && git add src/message_analytics.py src/combined_report.py src/html_report.py tests/test_message_analytics.py && git commit -m "feat(analytics): add trend analysis with 30-day rolling and year-over-year

Compute rolling 30-day message count vs previous 30 days with percentage
change. Add year-over-year comparison for current calendar month vs same
month last year. Display in message report, combined report, and HTML.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Thread Breakdown & Huddle-to-Message Ratio

**Files:**
- Modify: `src/message_analytics.py`
- Modify: `src/combined_report.py`
- Modify: `src/html_report.py`
- Modify: `tests/test_message_analytics.py`

- [ ] **Step 1: Write failing tests for thread breakdown**

Add to `/Users/devx/Projects/huddle/tests/test_message_analytics.py`:

```python
THREADED_MESSAGES = [
    # Top-level message (no thread_ts, or thread_ts == ts)
    {"user": "U_ME", "ts": "1700000000.000", "text": "top level 1", "subtype": None, "thread_ts": None},
    # Thread parent (thread_ts == own ts, has replies elsewhere)
    {"user": "U001", "ts": "1700000100.000", "text": "thread parent", "subtype": None, "thread_ts": "1700000100.000"},
    # Thread reply (thread_ts != own ts)
    {"user": "U_ME", "ts": "1700000150.000", "text": "reply to thread", "subtype": None, "thread_ts": "1700000100.000"},
    # Another thread reply
    {"user": "U001", "ts": "1700000200.000", "text": "another reply", "subtype": None, "thread_ts": "1700000100.000"},
    # Another top-level (no thread_ts)
    {"user": "U_ME", "ts": "1700000300.000", "text": "top level 2", "subtype": None},
    # Thread started by U_ME
    {"user": "U_ME", "ts": "1700000400.000", "text": "my thread parent", "subtype": None, "thread_ts": "1700000400.000"},
    {"user": "U001", "ts": "1700000450.000", "text": "reply to my thread", "subtype": None, "thread_ts": "1700000400.000"},
]


class TestThreadBreakdown:
    def test_top_level_count(self):
        stats = compute_message_stats(THREADED_MESSAGES, "U_ME")
        # Top-level: ts=1700000000 (thread_ts None), ts=1700000100 (thread_ts == ts),
        # ts=1700000300 (no thread_ts), ts=1700000400 (thread_ts == ts) = 4
        assert stats["top_level_messages"] == 4

    def test_thread_message_count(self):
        stats = compute_message_stats(THREADED_MESSAGES, "U_ME")
        # Thread replies: ts=1700000150 (thread_ts != ts), ts=1700000200, ts=1700000450 = 3
        assert stats["thread_messages"] == 3

    def test_thread_pct(self):
        stats = compute_message_stats(THREADED_MESSAGES, "U_ME")
        total = stats["total_messages"]
        expected_pct = round(3 / total * 100, 1)
        assert stats["thread_pct"] == expected_pct

    def test_threads_started_by_you(self):
        stats = compute_message_stats(THREADED_MESSAGES, "U_ME")
        # Thread parents started by U_ME: ts=1700000400 = 1
        assert stats["threads_started_by_you"] == 1

    def test_threads_started_by_them(self):
        stats = compute_message_stats(THREADED_MESSAGES, "U_ME")
        # Thread parents started by others: ts=1700000100 (U001) = 1
        assert stats["threads_started_by_them"] == 1

    def test_thread_keys_in_empty_stats(self):
        stats = compute_message_stats([], "U_ME")
        assert stats["top_level_messages"] == 0
        assert stats["thread_messages"] == 0
        assert stats["thread_pct"] == 0.0
        assert stats["threads_started_by_you"] == 0
        assert stats["threads_started_by_them"] == 0


class TestThreadDisplay:
    def test_format_message_report_includes_thread_section(self):
        stats = compute_message_stats(THREADED_MESSAGES, "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "Thread Activity" in output
        assert "Top-level:" in output
        assert "In threads:" in output

    def test_format_combined_report_includes_thread_section(self):
        from src.combined_report import format_combined_report
        m_stats = compute_message_stats(THREADED_MESSAGES, "U_ME")
        h_stats = {
            "total_huddles": 0, "total_seconds": 0, "avg_seconds": 0,
            "longest_seconds": 0, "shortest_seconds": 0, "median_seconds": 0,
            "huddles": [], "started_by_you": 0, "started_by_them": 0,
            "monthly_breakdown": {}, "weekday_breakdown": {},
        }
        output = format_combined_report(h_stats, m_stats, "DM with Alice")
        assert "Thread Activity" in output


class TestHuddleToMessageRatio:
    def test_ratio_computed_in_combined_report(self):
        from src.combined_report import format_combined_report
        m_stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        h_stats = {
            "total_huddles": 5, "total_seconds": 3600, "avg_seconds": 720,
            "longest_seconds": 1200, "shortest_seconds": 300, "median_seconds": 720,
            "huddles": [{"room": {"date_start": 1700000000}}] * 5,
            "started_by_you": 3, "started_by_them": 2,
            "monthly_breakdown": {}, "weekday_breakdown": {},
        }
        output = format_combined_report(h_stats, m_stats, "DM with Alice")
        assert "huddle" in output.lower()
        assert "message" in output.lower()
        # With 5 messages and 5 huddles: ratio is 1.0
        # The exact text: "For every huddle, ~1 messages exchanged" or similar
        assert "For every huddle" in output

    def test_ratio_not_shown_when_no_huddles(self):
        from src.combined_report import format_combined_report
        m_stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        h_stats = {
            "total_huddles": 0, "total_seconds": 0, "avg_seconds": 0,
            "longest_seconds": 0, "shortest_seconds": 0, "median_seconds": 0,
            "huddles": [], "started_by_you": 0, "started_by_them": 0,
            "monthly_breakdown": {}, "weekday_breakdown": {},
        }
        output = format_combined_report(h_stats, m_stats, "DM with Alice")
        assert "For every huddle" not in output
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_message_analytics.py::TestThreadBreakdown tests/test_message_analytics.py::TestThreadDisplay tests/test_message_analytics.py::TestHuddleToMessageRatio -v 2>&1 | tail -20
```

- [ ] **Step 3: Add thread breakdown computation to `compute_message_stats`**

In `/Users/devx/Projects/huddle/src/message_analytics.py`, add this computation block inside `compute_message_stats`, after the text emoji section and before the trend analysis section:

```python
    # --- Thread Breakdown ---
    top_level_messages = 0
    thread_messages = 0
    threads_started_by_you = 0
    threads_started_by_them = 0
    seen_thread_parents = set()

    for m in user_msgs:
        m_ts = m["ts"]
        m_thread_ts = m.get("thread_ts")
        if m_thread_ts is None or m_thread_ts == m_ts:
            # Top-level message or thread parent
            top_level_messages += 1
            # Check if this is a thread parent (thread_ts == ts means it started a thread)
            if m_thread_ts == m_ts and m_thread_ts not in seen_thread_parents:
                seen_thread_parents.add(m_thread_ts)
                if m["user"] == user_id:
                    threads_started_by_you += 1
                else:
                    threads_started_by_them += 1
        else:
            thread_messages += 1

    thread_pct = round(thread_messages / total * 100, 1) if total else 0.0
```

Add these keys to the empty-stats return dict:

```python
            "top_level_messages": 0,
            "thread_messages": 0,
            "thread_pct": 0.0,
            "threads_started_by_you": 0,
            "threads_started_by_them": 0,
```

Add these keys to the main return dict:

```python
        "top_level_messages": top_level_messages,
        "thread_messages": thread_messages,
        "thread_pct": thread_pct,
        "threads_started_by_you": threads_started_by_you,
        "threads_started_by_them": threads_started_by_them,
```

- [ ] **Step 4: Add thread breakdown display to `format_message_report`**

In `/Users/devx/Projects/huddle/src/message_analytics.py`, add a new section in `format_message_report`. Insert after the "Volume" section (and after the "Trends" section if it was added) but before "Who Initiates":

```python
    # Thread Activity
    if stats.get("thread_messages", 0) > 0 or stats.get("threads_started_by_you", 0) > 0:
        lines.append("")
        lines.append("Thread Activity")
        lines.append("-" * 50)
        lines.append(f"  Total messages:   {stats['total_messages']:,}")
        top_pct = round(stats["top_level_messages"] / stats["total_messages"] * 100) if stats["total_messages"] else 0
        thr_pct = round(stats["thread_messages"] / stats["total_messages"] * 100) if stats["total_messages"] else 0
        lines.append(f"  Top-level:        {stats['top_level_messages']:,} ({top_pct}%)")
        lines.append(f"  In threads:       {stats['thread_messages']:,} ({thr_pct}%)")
        lines.append(f"  Threads started:  {your_name}: {stats['threads_started_by_you']} / {their_name}: {stats['threads_started_by_them']}")
```

- [ ] **Step 5: Add thread breakdown and huddle-to-message ratio to `format_combined_report`**

In `/Users/devx/Projects/huddle/src/combined_report.py`, add a thread activity section after the "Messages" section (and after "Trends" if present), before "Who Initiates":

```python
    # --- Thread Activity ---
    if has_messages and (m_stats.get("thread_messages", 0) > 0 or m_stats.get("threads_started_by_you", 0) > 0):
        lines.append("Thread Activity")
        lines.append("-" * 55)
        top_pct = round(m_stats["top_level_messages"] / m_stats["total_messages"] * 100) if m_stats["total_messages"] else 0
        thr_pct = round(m_stats["thread_messages"] / m_stats["total_messages"] * 100) if m_stats["total_messages"] else 0
        lines.append(f"  Top-level:        {m_stats['top_level_messages']:,} ({top_pct}%)")
        lines.append(f"  In threads:       {m_stats['thread_messages']:,} ({thr_pct}%)")
        lines.append(f"  Threads started:  {your_name}: {m_stats['threads_started_by_you']} / {their_name}: {m_stats['threads_started_by_them']}")
        lines.append("")
```

Add the huddle-to-message ratio inside the existing "Frequency" section, after the existing `Messages/week` line:

```python
    # Huddle-to-message ratio (inside Frequency section)
    if has_huddles and has_messages and h_stats["total_huddles"] > 0:
        ratio = m_stats["total_messages"] / h_stats["total_huddles"]
        lines.append(f"  For every huddle, ~{ratio:.0f} messages exchanged")
```

- [ ] **Step 6: Add thread breakdown card to HTML report**

In `/Users/devx/Projects/huddle/src/html_report.py`, add a thread activity card after the trend card (or after the "Who Initiates" card if no trend):

```python
    # Thread activity card
    if has_messages and (m_stats.get("thread_messages", 0) > 0 or m_stats.get("threads_started_by_you", 0) > 0):
        top_pct = round(m_stats["top_level_messages"] / m_stats["total_messages"] * 100) if m_stats["total_messages"] else 0
        thr_pct = round(m_stats["thread_messages"] / m_stats["total_messages"] * 100) if m_stats["total_messages"] else 0
        thread_html = f"""
            <div class="stat-row"><span class="label">Top-level</span><span class="value">{m_stats['top_level_messages']:,} <small>({top_pct}%)</small></span></div>
            <div class="stat-row"><span class="label">In threads</span><span class="value">{m_stats['thread_messages']:,} <small>({thr_pct}%)</small></span></div>
            <div class="stat-row"><span class="label">Threads started</span><span class="value">{your_name}: {m_stats['threads_started_by_you']} &middot; {their_name}: {m_stats['threads_started_by_them']}</span></div>
        """
        cards.append(_card("Thread Activity", thread_html))
```

- [ ] **Step 7: Run all tests, confirm they pass**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_message_analytics.py -v
```

- [ ] **Step 8: Commit**

```bash
cd /Users/devx/Projects/huddle && git add src/message_analytics.py src/combined_report.py src/html_report.py tests/test_message_analytics.py && git commit -m "feat(analytics): add thread breakdown and huddle-to-message ratio

Thread breakdown splits messages into top-level and in-thread, tracks
who starts threads. Huddle-to-message ratio shown in combined report
Frequency section. Display in all three report formats.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Response Time by Hour & Link/File Sharing

**Files:**
- Modify: `src/message_analytics.py`
- Modify: `src/combined_report.py`
- Modify: `src/html_report.py`
- Modify: `tests/test_message_analytics.py`

- [ ] **Step 1: Write failing tests for response time by hour**

Add to `/Users/devx/Projects/huddle/tests/test_message_analytics.py`:

```python
def _make_messages_for_response_by_hour():
    """Create messages with known response times at specific hours.

    Conversation at 10:00 UTC — fast response (2 min):
      A sends at 10:00, B responds at 10:02, A responds at 10:04
    Conversation at 17:00 UTC — slow response (45 min):
      A sends at 17:00, B responds at 17:45
    Repeated enough to get >= 3 data points per hour.
    """
    base = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    messages = []

    for day_offset in range(5):
        day = base + timedelta(days=day_offset)

        # 10:00 conversation — B responds in 2 min
        t1 = day.replace(hour=10, minute=0).timestamp()
        t2 = day.replace(hour=10, minute=2).timestamp()
        t3 = day.replace(hour=10, minute=4).timestamp()
        messages.append({"user": "A", "ts": str(t1), "text": "hey", "subtype": None})
        messages.append({"user": "B", "ts": str(t2), "text": "hi", "subtype": None})
        messages.append({"user": "A", "ts": str(t3), "text": "ok", "subtype": None})

        # 17:00 conversation — B responds in 45 min
        t4 = day.replace(hour=17, minute=0).timestamp()
        t5 = day.replace(hour=17, minute=45).timestamp()
        messages.append({"user": "A", "ts": str(t4), "text": "question", "subtype": None})
        messages.append({"user": "B", "ts": str(t5), "text": "answer", "subtype": None})

    return messages


class TestResponseTimeByHour:
    def test_response_time_by_hour_keys(self):
        messages = _make_messages_for_response_by_hour()
        stats = compute_message_stats(messages, "A")
        assert "response_time_by_hour" in stats
        assert isinstance(stats["response_time_by_hour"], dict)

    def test_response_time_by_hour_has_correct_hours(self):
        messages = _make_messages_for_response_by_hour()
        stats = compute_message_stats(messages, "A")
        rt_by_hour = stats["response_time_by_hour"]
        # Should have entries for hour 10 (B responses at 10:02) and hour 17 (B responses at 17:45)
        assert 10 in rt_by_hour
        assert 17 in rt_by_hour

    def test_response_time_by_hour_fast_hour(self):
        messages = _make_messages_for_response_by_hour()
        stats = compute_message_stats(messages, "A")
        rt_by_hour = stats["response_time_by_hour"]
        # At 10:00, B responds in 120s each time
        assert rt_by_hour[10] == 120  # 2 minutes in seconds

    def test_response_time_by_hour_slow_hour(self):
        messages = _make_messages_for_response_by_hour()
        stats = compute_message_stats(messages, "A")
        rt_by_hour = stats["response_time_by_hour"]
        # At 17:00, B responds in 2700s (45 min) each time
        assert rt_by_hour[17] == 2700  # 45 minutes in seconds

    def test_response_time_by_hour_min_data_points(self):
        """Hours with < 3 data points are excluded."""
        base = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        messages = []
        # Only 2 responses at 14:00 — should be excluded
        for day_offset in range(2):
            day = base + timedelta(days=day_offset)
            t1 = day.replace(hour=14, minute=0).timestamp()
            t2 = day.replace(hour=14, minute=5).timestamp()
            messages.append({"user": "A", "ts": str(t1), "text": "hey", "subtype": None})
            messages.append({"user": "B", "ts": str(t2), "text": "hi", "subtype": None})
        stats = compute_message_stats(messages, "A")
        assert 14 not in stats["response_time_by_hour"]

    def test_response_time_by_hour_empty(self):
        stats = compute_message_stats([], "A")
        assert stats["response_time_by_hour"] == {}


class TestResponseTimeByHourDisplay:
    def test_format_message_report_includes_response_by_hour(self):
        messages = _make_messages_for_response_by_hour()
        stats = compute_message_stats(messages, "A")
        output = format_message_report(stats, "DM with Bob", your_name="Alice", their_name="Bob")
        assert "Response Time by Hour" in output
        assert "Fastest:" in output
        assert "Slowest:" in output
```

- [ ] **Step 2: Write failing tests for link & file sharing**

Add to `/Users/devx/Projects/huddle/tests/test_message_analytics.py`:

```python
MESSAGES_WITH_LINKS_AND_FILES = [
    {"user": "U_ME", "ts": "1.0", "text": "check <https://example.com|example> and <https://google.com>", "subtype": None, "files_count": 0},
    {"user": "U_ME", "ts": "2.0", "text": "here is <https://docs.com/page>", "subtype": None, "files_count": 2},
    {"user": "U001", "ts": "3.0", "text": "see <https://slack.com|Slack>", "subtype": None, "files_count": 1},
    {"user": "U001", "ts": "4.0", "text": "no links here", "subtype": None, "files_count": 0},
    {"user": "U_ME", "ts": "5.0", "text": "plain text", "subtype": None},
]


class TestLinkAndFileSharing:
    def test_your_links_shared(self):
        stats = compute_message_stats(MESSAGES_WITH_LINKS_AND_FILES, "U_ME")
        # U_ME: 2 links in msg 1, 1 link in msg 2 = 3
        assert stats["your_links_shared"] == 3

    def test_their_links_shared(self):
        stats = compute_message_stats(MESSAGES_WITH_LINKS_AND_FILES, "U_ME")
        # U001: 1 link in msg 3 = 1
        assert stats["their_links_shared"] == 1

    def test_your_files_shared(self):
        stats = compute_message_stats(MESSAGES_WITH_LINKS_AND_FILES, "U_ME")
        # U_ME: 0 + 2 = 2
        assert stats["your_files_shared"] == 2

    def test_their_files_shared(self):
        stats = compute_message_stats(MESSAGES_WITH_LINKS_AND_FILES, "U_ME")
        # U001: 1 + 0 = 1
        assert stats["their_files_shared"] == 1

    def test_link_file_keys_in_empty_stats(self):
        stats = compute_message_stats([], "U_ME")
        assert stats["your_links_shared"] == 0
        assert stats["their_links_shared"] == 0
        assert stats["your_files_shared"] == 0
        assert stats["their_files_shared"] == 0

    def test_no_files_count_field_treated_as_zero(self):
        """Messages without files_count (old cache) should count as 0 files."""
        msgs = [
            {"user": "U_ME", "ts": "1.0", "text": "hi", "subtype": None},
        ]
        stats = compute_message_stats(msgs, "U_ME")
        assert stats["your_files_shared"] == 0


class TestLinkFileDisplay:
    def test_format_message_report_includes_links_files(self):
        stats = compute_message_stats(MESSAGES_WITH_LINKS_AND_FILES, "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "Links & Files" in output

    def test_format_combined_report_includes_links_files(self):
        from src.combined_report import format_combined_report
        m_stats = compute_message_stats(MESSAGES_WITH_LINKS_AND_FILES, "U_ME")
        h_stats = {
            "total_huddles": 0, "total_seconds": 0, "avg_seconds": 0,
            "longest_seconds": 0, "shortest_seconds": 0, "median_seconds": 0,
            "huddles": [], "started_by_you": 0, "started_by_them": 0,
            "monthly_breakdown": {}, "weekday_breakdown": {},
        }
        output = format_combined_report(h_stats, m_stats, "DM with Alice")
        assert "Links & Files" in output
```

- [ ] **Step 3: Run tests, confirm they fail**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/test_message_analytics.py::TestResponseTimeByHour tests/test_message_analytics.py::TestResponseTimeByHourDisplay tests/test_message_analytics.py::TestLinkAndFileSharing tests/test_message_analytics.py::TestLinkFileDisplay -v 2>&1 | tail -30
```

- [ ] **Step 4: Add response-time-by-hour computation to `compute_message_stats`**

In `/Users/devx/Projects/huddle/src/message_analytics.py`, add this computation block inside `compute_message_stats`, after the existing response time computation (after `their_median_resp = _median(their_response_times)`) and before the time breakdowns section:

```python
    # --- Response Time by Hour ---
    # Group all response times by the hour of the response
    from collections import defaultdict
    response_times_by_hour: dict[int, list[int]] = defaultdict(list)
    for i in range(1, len(turns)):
        prev_turn = turns[i - 1]
        curr_turn = turns[i]
        delta = int(curr_turn["start_ts"] - prev_turn["start_ts"])
        if delta >= INITIATION_GAP_SECONDS:
            continue
        if prev_turn["user"] != curr_turn["user"]:
            response_hour = datetime.fromtimestamp(curr_turn["start_ts"], tz=timezone.utc).astimezone().hour
            response_times_by_hour[response_hour].append(delta)

    # Only include hours with >= 3 data points
    response_time_by_hour = {}
    for hour, times in sorted(response_times_by_hour.items()):
        if len(times) >= 3:
            response_time_by_hour[hour] = _median(times)
```

Note: Move the `from collections import defaultdict` to the top of the file if preferred, or use it inline. Since `Counter` is already imported from `collections`, just add `defaultdict` to the existing import:

```python
from collections import Counter, defaultdict
```

Add this key to the empty-stats return dict:

```python
            "response_time_by_hour": {},
```

Add this key to the main return dict:

```python
        "response_time_by_hour": response_time_by_hour,
```

- [ ] **Step 5: Add link & file sharing computation to `compute_message_stats`**

In `/Users/devx/Projects/huddle/src/message_analytics.py`, add this computation block inside `compute_message_stats`, after the thread breakdown section and before the trend analysis section:

```python
    # --- Link & File Sharing ---
    _LINK_COUNT_RE = re.compile(r"<https?://[^>]+>")
    your_links_shared = 0
    their_links_shared = 0
    your_files_shared = 0
    their_files_shared = 0
    for m in user_msgs:
        links = len(_LINK_COUNT_RE.findall(m.get("text", "")))
        files = m.get("files_count", 0)
        if m["user"] == user_id:
            your_links_shared += links
            your_files_shared += files
        else:
            their_links_shared += links
            their_files_shared += files
```

Add these keys to the empty-stats return dict:

```python
            "your_links_shared": 0,
            "their_links_shared": 0,
            "your_files_shared": 0,
            "their_files_shared": 0,
```

Add these keys to the main return dict:

```python
        "your_links_shared": your_links_shared,
        "their_links_shared": their_links_shared,
        "your_files_shared": your_files_shared,
        "their_files_shared": their_files_shared,
```

- [ ] **Step 6: Add response-by-hour display to `format_message_report`**

In `/Users/devx/Projects/huddle/src/message_analytics.py`, add a new section to `format_message_report`. Insert after the "Response Time" section and before the "Message Style" section:

```python
    # Response Time by Hour
    rt_by_hour = stats.get("response_time_by_hour", {})
    if rt_by_hour:
        lines.append("")
        lines.append("Response Time by Hour")
        lines.append("-" * 50)
        fastest_hour = min(rt_by_hour, key=rt_by_hour.get)
        slowest_hour = max(rt_by_hour, key=rt_by_hour.get)
        lines.append(f"  Fastest:          {fastest_hour:02d}:00 ({format_duration(rt_by_hour[fastest_hour])} median)")
        lines.append(f"  Slowest:          {slowest_hour:02d}:00 ({format_duration(rt_by_hour[slowest_hour])} median)")
```

- [ ] **Step 7: Add links & files display to `format_message_report`**

In `/Users/devx/Projects/huddle/src/message_analytics.py`, add a new section to `format_message_report`. Insert after the "Emojis Used in Messages" section and before the "Reactions on Messages" section:

```python
    # Links & Files
    has_links_files = (
        stats.get("your_links_shared", 0) > 0 or stats.get("their_links_shared", 0) > 0
        or stats.get("your_files_shared", 0) > 0 or stats.get("their_files_shared", 0) > 0
    )
    if has_links_files:
        lines.append("")
        lines.append("Links & Files")
        lines.append("-" * 50)
        lines.append(f"  {your_name + ':':<16} {stats['your_links_shared']:,} links, {stats['your_files_shared']:,} files")
        lines.append(f"  {their_name + ':':<16} {stats['their_links_shared']:,} links, {stats['their_files_shared']:,} files")
```

- [ ] **Step 8: Add response-by-hour and links & files to `format_combined_report`**

In `/Users/devx/Projects/huddle/src/combined_report.py`, add a response-by-hour section after the existing "Response Time (Messages)" section:

```python
    # --- Response Time by Hour ---
    if has_messages:
        rt_by_hour = m_stats.get("response_time_by_hour", {})
        if rt_by_hour:
            lines.append("Response Time by Hour")
            lines.append("-" * 55)
            fastest_hour = min(rt_by_hour, key=rt_by_hour.get)
            slowest_hour = max(rt_by_hour, key=rt_by_hour.get)
            lines.append(f"  Fastest:          {fastest_hour:02d}:00 ({format_duration(rt_by_hour[fastest_hour])} median)")
            lines.append(f"  Slowest:          {slowest_hour:02d}:00 ({format_duration(rt_by_hour[slowest_hour])} median)")
            lines.append("")
```

Add a links & files section after the "Emojis Used in Messages" section:

```python
    # --- Links & Files ---
    has_links_files = has_messages and (
        m_stats.get("your_links_shared", 0) > 0 or m_stats.get("their_links_shared", 0) > 0
        or m_stats.get("your_files_shared", 0) > 0 or m_stats.get("their_files_shared", 0) > 0
    )
    if has_links_files:
        lines.append("Links & Files")
        lines.append("-" * 55)
        lines.append(f"  {your_name + ':':<16} {m_stats['your_links_shared']:,} links, {m_stats['your_files_shared']:,} files")
        lines.append(f"  {their_name + ':':<16} {m_stats['their_links_shared']:,} links, {m_stats['their_files_shared']:,} files")
        lines.append("")
```

- [ ] **Step 9: Add response-by-hour chart and links & files card to HTML report**

In `/Users/devx/Projects/huddle/src/html_report.py`, add chart data for response-by-hour near the top of `generate_html_report` (alongside other chart data preparations):

```python
    # Response by hour chart data
    rt_by_hour = m_stats.get("response_time_by_hour", {}) if has_messages else {}
    rt_hour_labels = json.dumps([f"{h:02d}:00" for h in range(24)])
    rt_hour_data = json.dumps([rt_by_hour.get(h, 0) / 60 for h in range(24)])  # convert to minutes
```

Add a response-by-hour chart card in the HTML body, after the "By Hour of Day" chart:

```python
{"" if not rt_by_hour else f'''
<div class="chart-card">
  <h2>Median Response Time by Hour (minutes)</h2>
  <canvas id="rtByHourChart"></canvas>
</div>
'''}
```

Add the Chart.js initialization for this chart in the `<script>` section:

```javascript
{"" if not rt_by_hour else f"""
new Chart(document.getElementById('rtByHourChart'), {{
  type: 'bar',
  data: {{
    labels: {rt_hour_labels},
    datasets: [{{
      label: 'Median Response (min)',
      data: {rt_hour_data},
      backgroundColor: 'rgba(63,185,80,0.6)',
      borderRadius: 6,
      borderSkipped: false,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#161b22' }}, title: {{ display: true, text: 'Minutes', color: '#3fb950', font: {{ size: 11 }} }} }}, x: {{ grid: {{ display: false }}, ticks: {{ maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }} }} }}
  }}
}});
"""}
```

Add a links & files card to the cards section:

```python
    # Links & Files card
    if has_messages:
        has_links_files = (
            m_stats.get("your_links_shared", 0) > 0 or m_stats.get("their_links_shared", 0) > 0
            or m_stats.get("your_files_shared", 0) > 0 or m_stats.get("their_files_shared", 0) > 0
        )
        if has_links_files:
            lf_html = f"""
                <div class="stat-row"><span class="label">{your_name}</span><span class="value">{m_stats['your_links_shared']:,} links &middot; {m_stats['your_files_shared']:,} files</span></div>
                <div class="stat-row"><span class="label">{their_name}</span><span class="value">{m_stats['their_links_shared']:,} links &middot; {m_stats['their_files_shared']:,} files</span></div>
            """
            cards.append(_card("Links & Files", lf_html))
```

- [ ] **Step 10: Run all tests, confirm they pass**

```bash
cd /Users/devx/Projects/huddle && python -m pytest tests/ -v
```

- [ ] **Step 11: Commit**

```bash
cd /Users/devx/Projects/huddle && git add src/message_analytics.py src/combined_report.py src/html_report.py tests/test_message_analytics.py && git commit -m "feat(analytics): add response-time-by-hour and link/file sharing stats

Response-time-by-hour groups turn-based response times by the hour of
response, computes median per hour (min 3 data points), and reports
fastest/slowest hours. Link sharing counts Slack-format URLs per user.
File sharing sums files_count per user. All displayed in console reports
and HTML with a bar chart for response-by-hour.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
