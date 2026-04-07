# Caching & Message Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent message cache so repeated runs are fast, a generic message fetcher, and message analytics (volume, who initiates, response times, active hours, message style). Add `--no-cache` and `--clear-cache` CLI flags.

**Architecture:** New `CacheManager` stores trimmed messages as JSON per channel in `.cache/`. `SlackClient` gains a `fetch_messages()` method that fetches all messages (not just huddles). `main.py` gets argparse and a two-choice analytics menu (huddles vs messages). Huddle analytics now derives from cached messages instead of its own fetch. Message analytics lives in a new `message_analytics.py`.

**Tech Stack:** Python 3.10+, `requests`, `python-dotenv`, `pytest`, `json` (stdlib)

---

## File Map

| File | Change | Responsibility |
|---|---|---|
| `src/cache.py` | Create | Read/write/clear JSON message cache per channel |
| `src/slack_client.py` | Modify | Add `fetch_messages(channel_id, oldest=None)` generic fetcher |
| `src/message_analytics.py` | Create | Compute message stats + format message report |
| `src/report.py` | Modify | `extract_huddles(messages)` helper; existing stats/format unchanged |
| `src/main.py` | Modify | argparse (`--no-cache`, `--clear-cache`), analytics menu, cache integration |
| `.gitignore` | Modify | Add `.cache/` |
| `tests/test_cache.py` | Create | Tests for CacheManager |
| `tests/test_slack_client.py` | Modify | Add tests for fetch_messages |
| `tests/test_message_analytics.py` | Create | Tests for message stats + formatting |
| `tests/test_report.py` | Modify | Add test for extract_huddles |
| `tests/test_main.py` | Modify | Update for new flow |

---

### Task 1: Cache Manager

**Files:**
- Create: `src/cache.py`
- Create: `tests/test_cache.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add `.cache/` to `.gitignore`**

Append `.cache/` to `/Users/devx/Projects/huddle/.gitignore`.

- [ ] **Step 2: Write failing tests for CacheManager**

```python
# tests/test_cache.py
import json
import os
import tempfile
from src.cache import CacheManager


class TestCacheManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cm = CacheManager(cache_dir=self.tmpdir)

    def test_no_cache_returns_none(self):
        result = self.cm.load("D001")
        assert result is None

    def test_save_and_load(self):
        messages = [
            {"user": "U001", "ts": "1700000000.000000", "text": "hello", "subtype": None},
            {"user": "U002", "ts": "1700000060.000000", "text": "hey!", "subtype": None},
        ]
        self.cm.save("D001", messages, last_ts="1700000060.000000")
        result = self.cm.load("D001")

        assert result is not None
        assert result["last_ts"] == "1700000060.000000"
        assert len(result["messages"]) == 2
        assert result["messages"][0]["text"] == "hello"

    def test_append_merges_new_messages(self):
        old = [
            {"user": "U001", "ts": "1700000000.000000", "text": "hello", "subtype": None},
        ]
        self.cm.save("D001", old, last_ts="1700000000.000000")

        new = [
            {"user": "U002", "ts": "1700000060.000000", "text": "hey!", "subtype": None},
        ]
        self.cm.append("D001", new, last_ts="1700000060.000000")

        result = self.cm.load("D001")
        assert len(result["messages"]) == 2
        assert result["last_ts"] == "1700000060.000000"

    def test_clear_specific_channel(self):
        self.cm.save("D001", [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}], last_ts="1.0")
        self.cm.save("D002", [{"user": "U001", "ts": "2.0", "text": "b", "subtype": None}], last_ts="2.0")
        self.cm.clear("D001")

        assert self.cm.load("D001") is None
        assert self.cm.load("D002") is not None

    def test_clear_all(self):
        self.cm.save("D001", [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}], last_ts="1.0")
        self.cm.save("D002", [{"user": "U001", "ts": "2.0", "text": "b", "subtype": None}], last_ts="2.0")
        self.cm.clear_all()

        assert self.cm.load("D001") is None
        assert self.cm.load("D002") is None

    def test_trim_message_strips_extra_fields(self):
        msg = {
            "user": "U001",
            "ts": "1700000000.000000",
            "text": "hello",
            "subtype": "huddle_thread",
            "room": {"date_start": 100, "date_end": 200, "has_ended": True, "participant_history": ["U001"], "created_by": "U001"},
            "blocks": [{"type": "rich_text"}],
            "team": "T123",
            "extra_field": "should be dropped",
        }
        trimmed = CacheManager.trim_message(msg)
        assert trimmed["user"] == "U001"
        assert trimmed["ts"] == "1700000000.000000"
        assert trimmed["text"] == "hello"
        assert trimmed["subtype"] == "huddle_thread"
        assert trimmed["room"]["date_start"] == 100
        assert "blocks" not in trimmed
        assert "team" not in trimmed
        assert "extra_field" not in trimmed

    def test_trim_message_without_room(self):
        msg = {"user": "U001", "ts": "1.0", "text": "hi", "type": "message"}
        trimmed = CacheManager.trim_message(msg)
        assert "room" not in trimmed
        assert trimmed["user"] == "U001"

    def test_corrupted_cache_returns_none(self):
        path = os.path.join(self.tmpdir, "D001.json")
        with open(path, "w") as f:
            f.write("not valid json{{{")
        result = self.cm.load("D001")
        assert result is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `source venv/bin/activate && pytest tests/test_cache.py -v`
Expected: FAIL — ImportError

- [ ] **Step 4: Implement CacheManager**

```python
# src/cache.py
import json
import os


class CacheManager:
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = cache_dir

    def _path(self, channel_id: str) -> str:
        return os.path.join(self.cache_dir, f"{channel_id}.json")

    @staticmethod
    def trim_message(msg: dict) -> dict:
        trimmed = {
            "user": msg.get("user"),
            "ts": msg.get("ts"),
            "text": msg.get("text", ""),
            "subtype": msg.get("subtype"),
        }
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

    def load(self, channel_id: str) -> dict | None:
        path = self._path(channel_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            return None

    def save(self, channel_id: str, messages: list[dict], last_ts: str):
        os.makedirs(self.cache_dir, exist_ok=True)
        data = {
            "channel_id": channel_id,
            "last_ts": last_ts,
            "messages": messages,
        }
        with open(self._path(channel_id), "w") as f:
            json.dump(data, f)

    def append(self, channel_id: str, new_messages: list[dict], last_ts: str):
        existing = self.load(channel_id)
        if existing is None:
            self.save(channel_id, new_messages, last_ts)
            return
        existing["messages"].extend(new_messages)
        existing["last_ts"] = last_ts
        with open(self._path(channel_id), "w") as f:
            json.dump(existing, f)

    def clear(self, channel_id: str):
        path = self._path(channel_id)
        if os.path.exists(path):
            os.remove(path)

    def clear_all(self):
        if not os.path.exists(self.cache_dir):
            return
        for fname in os.listdir(self.cache_dir):
            if fname.endswith(".json"):
                os.remove(os.path.join(self.cache_dir, fname))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cache.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add .gitignore src/cache.py tests/test_cache.py
git commit -m "feat: add CacheManager for persistent message storage"
```

---

### Task 2: Generic Message Fetcher

**Files:**
- Modify: `src/slack_client.py`
- Modify: `tests/test_slack_client.py`

- [ ] **Step 1: Write failing tests for `fetch_messages`**

Add to `tests/test_slack_client.py`:

```python
class TestFetchMessages:
    def test_fetches_all_messages(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {"type": "message", "user": "U001", "ts": "1700000060.000", "text": "world"},
                {"type": "message", "user": "U_ME", "ts": "1700000000.000", "text": "hello"},
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(history_response)):
            messages = client.fetch_messages("C12345")

        assert len(messages) == 2

    def test_fetches_with_oldest_param(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {"type": "message", "user": "U001", "ts": "1700000120.000", "text": "new msg"},
            ],
            "has_more": False,
        }
        mock_get = MagicMock(return_value=_mock_response(history_response))
        with patch("src.slack_client.requests.get", mock_get):
            messages = client.fetch_messages("C12345", oldest="1700000060.000")

        call_params = mock_get.call_args[1]["params"]
        assert call_params["oldest"] == "1700000060.000"
        assert len(messages) == 1

    def test_paginates_messages(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        page1 = {
            "ok": True,
            "messages": [{"type": "message", "user": "U001", "ts": "2.0", "text": "b"}],
            "has_more": True,
            "response_metadata": {"next_cursor": "cursor_abc"},
        }
        page2 = {
            "ok": True,
            "messages": [{"type": "message", "user": "U_ME", "ts": "1.0", "text": "a"}],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", side_effect=[_mock_response(page1), _mock_response(page2)]):
            messages = client.fetch_messages("C12345")

        assert len(messages) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_slack_client.py::TestFetchMessages -v`
Expected: FAIL — AttributeError

- [ ] **Step 3: Implement `fetch_messages`**

Add to `SlackClient` in `src/slack_client.py`, replace `fetch_huddles` with:

```python
    def fetch_messages(self, channel_id: str, oldest: str | None = None) -> list[dict]:
        messages = []
        cursor = ""
        page = 0
        while True:
            page += 1
            _print_status(f"Fetching messages... (page {page}, {len(messages)} fetched)")
            params = {"channel": channel_id, "limit": 200}
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
        return messages
```

Also keep `fetch_huddles` for backwards compatibility but make it use `fetch_messages` internally:

```python
    def fetch_huddles(self, channel_id: str) -> list[dict]:
        messages = self.fetch_messages(channel_id)
        huddles = []
        for msg in messages:
            if msg.get("subtype") != "huddle_thread":
                continue
            room = msg.get("room", {})
            if not room.get("has_ended"):
                continue
            huddles.append(msg)
        return huddles
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `pytest tests/test_slack_client.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slack_client.py tests/test_slack_client.py
git commit -m "feat: add generic fetch_messages with oldest param for incremental fetching"
```

---

### Task 3: Extract Huddles Helper in Report

**Files:**
- Modify: `src/report.py`
- Modify: `tests/test_report.py`

- [ ] **Step 1: Write failing test for `extract_huddles`**

Add to `tests/test_report.py`:

```python
from src.report import format_duration, compute_stats, format_report, extract_huddles


class TestExtractHuddles:
    def test_extracts_ended_huddles(self):
        messages = [
            {"user": "U001", "ts": "1.0", "text": "hello", "subtype": None},
            {"user": None, "ts": "2.0", "text": "", "subtype": "huddle_thread", "room": {
                "date_start": 1000, "date_end": 2000, "has_ended": True,
                "participant_history": ["U001", "U002"], "created_by": "U001",
            }},
            {"user": "U002", "ts": "3.0", "text": "bye", "subtype": None},
        ]
        huddles = extract_huddles(messages)
        assert len(huddles) == 1
        assert huddles[0]["room"]["date_start"] == 1000

    def test_skips_ongoing_huddles(self):
        messages = [
            {"user": None, "ts": "1.0", "text": "", "subtype": "huddle_thread", "room": {
                "date_start": 1000, "date_end": 0, "has_ended": False,
                "participant_history": ["U001"], "created_by": "U001",
            }},
        ]
        huddles = extract_huddles(messages)
        assert len(huddles) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py::TestExtractHuddles -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement `extract_huddles`**

Add to `src/report.py` (before `compute_stats`):

```python
def extract_huddles(messages: list[dict]) -> list[dict]:
    huddles = []
    for msg in messages:
        if msg.get("subtype") != "huddle_thread":
            continue
        room = msg.get("room", {})
        if not room.get("has_ended"):
            continue
        huddles.append(msg)
    return huddles
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_report.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/report.py tests/test_report.py
git commit -m "feat: add extract_huddles helper for working from cached messages"
```

---

### Task 4: Message Analytics

**Files:**
- Create: `src/message_analytics.py`
- Create: `tests/test_message_analytics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_message_analytics.py
from src.message_analytics import compute_message_stats, format_message_report


SAMPLE_MESSAGES = [
    {"user": "U_ME", "ts": "1700000000.000", "text": "hey there how are you", "subtype": None},
    {"user": "U001", "ts": "1700000300.000", "text": "good thanks", "subtype": None},
    {"user": "U_ME", "ts": "1700000600.000", "text": "cool", "subtype": None},
    {"user": "U001", "ts": "1700086700.000", "text": "morning", "subtype": None},
    {"user": "U_ME", "ts": "1700087000.000", "text": "hi good morning how is it going", "subtype": None},
    # System messages should be excluded
    {"user": None, "ts": "1700087500.000", "text": "", "subtype": "huddle_thread", "room": {}},
    {"user": "USLACKBOT", "ts": "1700088000.000", "text": "joined", "subtype": "channel_join"},
]


class TestComputeMessageStats:
    def test_counts_messages(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["total_messages"] == 5
        assert stats["you_count"] == 3
        assert stats["them_count"] == 2

    def test_excludes_system_messages(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        # huddle_thread and channel_join should be excluded
        assert stats["total_messages"] == 5

    def test_percentages(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["you_pct"] == 60.0
        assert stats["them_pct"] == 40.0

    def test_avg_word_count(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        # You: "hey there how are you" (5), "cool" (1), "hi good morning how is it going" (7) = avg 4.3
        # Them: "good thanks" (2), "morning" (1) = avg 1.5
        assert stats["your_avg_words"] == 4.3
        assert stats["their_avg_words"] == 1.5

    def test_initiations(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        # First message by U_ME, then gap > 4hrs before U001 says "morning"
        # So U_ME initiates 1, U001 initiates 1
        assert stats["you_initiated"] == 1
        assert stats["them_initiated"] == 1

    def test_response_times(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        # U_ME -> U001 reply at +300s = 5min
        # U001 -> U_ME reply at +300s = 5min
        # U001 -> U_ME reply at +300s = 5min (morning -> hi good morning)
        assert stats["your_avg_response_seconds"] > 0
        assert stats["their_avg_response_seconds"] > 0

    def test_empty_messages(self):
        stats = compute_message_stats([], "U_ME")
        assert stats["total_messages"] == 0
        assert stats["you_count"] == 0

    def test_weekday_breakdown(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert isinstance(stats["weekday_breakdown"], dict)
        assert sum(stats["weekday_breakdown"].values()) == 5

    def test_hourly_breakdown(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert isinstance(stats["hourly_breakdown"], dict)
        assert sum(stats["hourly_breakdown"].values()) == 5


class TestFormatMessageReport:
    def test_formats_report(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        output = format_message_report(stats, "DM with Alice")

        assert "Message Analytics" in output
        assert "DM with Alice" in output
        assert "Total messages:" in output
        assert "You:" in output
        assert "Them:" in output
        assert "Who Initiates" in output
        assert "Response Time" in output
        assert "Message Style" in output
        assert "Most Active Hours" in output
        assert "By Day of Week" in output

    def test_formats_empty_report(self):
        stats = compute_message_stats([], "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "No messages found" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_message_analytics.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement message analytics**

```python
# src/message_analytics.py
from collections import Counter
from datetime import datetime, timezone

from src.report import format_duration

SYSTEM_SUBTYPES = {
    "huddle_thread", "channel_join", "channel_leave", "channel_topic",
    "channel_purpose", "channel_name", "bot_message", "bot_add",
    "bot_remove", "file_share", "file_comment", "file_mention",
    "pinned_item", "unpinned_item", "group_join", "group_leave",
    "group_topic", "group_purpose", "group_name", "channel_archive",
    "channel_unarchive", "ekm_access_denied", "reminder_add",
    "sh_room_created",
}

INITIATION_GAP_SECONDS = 4 * 3600  # 4 hours


def _filter_user_messages(messages: list[dict]) -> list[dict]:
    return [
        m for m in messages
        if m.get("subtype") not in SYSTEM_SUBTYPES
        and m.get("user") is not None
        and m.get("user") != "USLACKBOT"
    ]


def compute_message_stats(messages: list[dict], user_id: str) -> dict:
    user_msgs = _filter_user_messages(messages)

    if not user_msgs:
        return {
            "total_messages": 0,
            "you_count": 0, "them_count": 0,
            "you_pct": 0.0, "them_pct": 0.0,
            "your_avg_words": 0.0, "their_avg_words": 0.0,
            "you_initiated": 0, "them_initiated": 0,
            "your_avg_response_seconds": 0, "their_avg_response_seconds": 0,
            "weekday_breakdown": {}, "hourly_breakdown": {},
            "span_days": 0, "first_ts": 0, "last_ts": 0,
        }

    you_msgs = [m for m in user_msgs if m["user"] == user_id]
    them_msgs = [m for m in user_msgs if m["user"] != user_id]
    total = len(user_msgs)

    # Word counts
    you_words = [len(m.get("text", "").split()) for m in you_msgs] if you_msgs else [0]
    them_words = [len(m.get("text", "").split()) for m in them_msgs] if them_msgs else [0]

    # Sort by timestamp for sequential analysis
    sorted_msgs = sorted(user_msgs, key=lambda m: float(m["ts"]))

    # Initiations: first message after a gap > INITIATION_GAP_SECONDS
    you_initiated = 0
    them_initiated = 0
    if sorted_msgs:
        first = sorted_msgs[0]
        if first["user"] == user_id:
            you_initiated += 1
        else:
            them_initiated += 1
        for i in range(1, len(sorted_msgs)):
            gap = float(sorted_msgs[i]["ts"]) - float(sorted_msgs[i - 1]["ts"])
            if gap >= INITIATION_GAP_SECONDS:
                if sorted_msgs[i]["user"] == user_id:
                    you_initiated += 1
                else:
                    them_initiated += 1

    # Response times
    your_response_times = []
    their_response_times = []
    for i in range(1, len(sorted_msgs)):
        prev = sorted_msgs[i - 1]
        curr = sorted_msgs[i]
        delta = float(curr["ts"]) - float(prev["ts"])
        if delta >= INITIATION_GAP_SECONDS:
            continue
        if prev["user"] != user_id and curr["user"] == user_id:
            your_response_times.append(delta)
        elif prev["user"] == user_id and curr["user"] != user_id:
            their_response_times.append(delta)

    your_avg_resp = int(sum(your_response_times) / len(your_response_times)) if your_response_times else 0
    their_avg_resp = int(sum(their_response_times) / len(their_response_times)) if their_response_times else 0

    # Time breakdowns
    weekday: Counter[str] = Counter()
    hourly: Counter[int] = Counter()
    timestamps = []
    for m in sorted_msgs:
        dt = datetime.fromtimestamp(float(m["ts"]), tz=timezone.utc).astimezone()
        weekday[dt.strftime("%A")] += 1
        hourly[dt.hour] += 1
        timestamps.append(float(m["ts"]))

    span_days = 0
    if len(timestamps) >= 2:
        first_dt = datetime.fromtimestamp(timestamps[0], tz=timezone.utc).astimezone()
        last_dt = datetime.fromtimestamp(timestamps[-1], tz=timezone.utc).astimezone()
        span_days = (last_dt - first_dt).days + 1

    return {
        "total_messages": total,
        "you_count": len(you_msgs),
        "them_count": len(them_msgs),
        "you_pct": round(len(you_msgs) / total * 100, 1) if total else 0.0,
        "them_pct": round(len(them_msgs) / total * 100, 1) if total else 0.0,
        "your_avg_words": round(sum(you_words) / len(you_words), 1) if you_words else 0.0,
        "their_avg_words": round(sum(them_words) / len(them_words), 1) if them_words else 0.0,
        "you_initiated": you_initiated,
        "them_initiated": them_initiated,
        "your_avg_response_seconds": your_avg_resp,
        "their_avg_response_seconds": their_avg_resp,
        "weekday_breakdown": dict(weekday),
        "hourly_breakdown": dict(sorted(hourly.items())),
        "span_days": span_days,
        "first_ts": timestamps[0] if timestamps else 0,
        "last_ts": timestamps[-1] if timestamps else 0,
    }


def format_message_report(stats: dict, channel_label: str) -> str:
    if stats["total_messages"] == 0:
        return f"\nMessage Analytics\n=================\nChannel: {channel_label}\n\nNo messages found.\n"

    lines = []
    lines.append("")
    lines.append("Message Analytics")
    lines.append("=" * 50)
    lines.append(f"Channel:  {channel_label}")

    if stats["first_ts"] and stats["last_ts"]:
        first_date = datetime.fromtimestamp(stats["first_ts"], tz=timezone.utc).astimezone()
        last_date = datetime.fromtimestamp(stats["last_ts"], tz=timezone.utc).astimezone()
        lines.append(f"Period:   {first_date.strftime('%Y-%m-%d')} -> {last_date.strftime('%Y-%m-%d')} ({stats['span_days']} days)")
    lines.append("")

    # Volume
    lines.append("Volume")
    lines.append("-" * 50)
    lines.append(f"  Total messages:   {stats['total_messages']:,}")
    lines.append(f"  You:              {stats['you_count']:,} ({stats['you_pct']:.0f}%)")
    lines.append(f"  Them:             {stats['them_count']:,} ({stats['them_pct']:.0f}%)")
    if stats["span_days"] > 0:
        per_week = stats["total_messages"] / max(stats["span_days"] / 7, 1)
        lines.append(f"  Per week:         {per_week:.1f} messages")

    # Who initiates
    total_init = stats["you_initiated"] + stats["them_initiated"]
    if total_init > 0:
        lines.append("")
        lines.append("Who Initiates")
        lines.append("-" * 50)
        you_init_pct = stats["you_initiated"] / total_init * 100
        them_init_pct = stats["them_initiated"] / total_init * 100
        lines.append(f"  You:              {stats['you_initiated']} ({you_init_pct:.0f}%)")
        lines.append(f"  Them:             {stats['them_initiated']} ({them_init_pct:.0f}%)")
        lines.append(f"  (gap threshold: 4 hours)")

    # Response time
    if stats["your_avg_response_seconds"] > 0 or stats["their_avg_response_seconds"] > 0:
        lines.append("")
        lines.append("Response Time")
        lines.append("-" * 50)
        lines.append(f"  Your avg reply:   {format_duration(stats['your_avg_response_seconds'])}")
        lines.append(f"  Their avg reply:  {format_duration(stats['their_avg_response_seconds'])}")

    # Message style
    lines.append("")
    lines.append("Message Style")
    lines.append("-" * 50)
    lines.append(f"  Your avg length:  {stats['your_avg_words']:.1f} words")
    lines.append(f"  Their avg length: {stats['their_avg_words']:.1f} words")

    # Hourly breakdown - top 5 hours
    hourly = stats.get("hourly_breakdown", {})
    if hourly:
        lines.append("")
        lines.append("Most Active Hours")
        lines.append("-" * 50)
        top_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)[:5]
        top_hours.sort(key=lambda x: x[0])
        max_count = max(c for _, c in top_hours) if top_hours else 1
        for hour, count in top_hours:
            bar_len = int(count / max_count * 20)
            bar = "#" * bar_len
            label = f"{hour:02d}:00"
            lines.append(f"  {label}  {bar:<20}  ({count:,})")

    # Day of week
    weekday = stats.get("weekday_breakdown", {})
    if weekday:
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        sorted_days = sorted(weekday.items(), key=lambda x: day_order.index(x[0]) if x[0] in day_order else 7)
        max_count = max(c for _, c in sorted_days) if sorted_days else 1
        lines.append("")
        lines.append("By Day of Week")
        lines.append("-" * 50)
        for day, count in sorted_days:
            bar_len = int(count / max_count * 20)
            bar = "#" * bar_len
            lines.append(f"  {day:<12} {count:>5,}  {bar}")

    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_message_analytics.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/message_analytics.py tests/test_message_analytics.py
git commit -m "feat: add message analytics with volume, initiations, response times, style"
```

---

### Task 5: Main Flow Refactor — Cache + Analytics Menu + CLI Flags

**Files:**
- Modify: `src/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing tests for new flow helpers**

Replace `tests/test_main.py` with:

```python
# tests/test_main.py
from src.main import build_search_results, parse_args


class TestBuildSearchResults:
    def test_combines_dm_and_channel_results(self):
        users = [
            {"id": "U001", "real_name": "John Smith"},
            {"id": "U002", "real_name": "Johnny B"},
        ]
        dm_channels = [
            {"id": "D001", "user": "U001"},
            {"id": "D003", "user": "U003"},
        ]
        channels = [
            {"id": "C001", "name": "john-project"},
        ]
        results = build_search_results(users, dm_channels, channels)

        assert len(results) == 2
        assert results[0] == {"channel_id": "D001", "label": "John Smith (DM)"}
        assert results[1] == {"channel_id": "C001", "label": "#john-project (channel)"}

    def test_skips_users_without_dm(self):
        users = [
            {"id": "U001", "real_name": "John Smith"},
            {"id": "U002", "real_name": "Johnny B"},
        ]
        dm_channels = [
            {"id": "D001", "user": "U001"},
        ]
        channels = []
        results = build_search_results(users, dm_channels, channels)

        assert len(results) == 1
        assert results[0]["label"] == "John Smith (DM)"


class TestParseArgs:
    def test_default_args(self):
        args = parse_args([])
        assert args.no_cache is False
        assert args.clear_cache is False

    def test_no_cache_flag(self):
        args = parse_args(["--no-cache"])
        assert args.no_cache is True

    def test_clear_cache_flag(self):
        args = parse_args(["--clear-cache"])
        assert args.clear_cache is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — cannot import `parse_args`

- [ ] **Step 3: Implement updated main.py**

```python
# src/main.py
import argparse
import os
import sys
from dotenv import load_dotenv
from src.cache import CacheManager
from src.slack_client import SlackClient
from src.report import extract_huddles, compute_stats, format_report
from src.message_analytics import compute_message_stats, format_message_report


def build_search_results(
    users: list[dict],
    dm_channels: list[dict],
    channels: list[dict],
) -> list[dict]:
    dm_by_user = {ch["user"]: ch["id"] for ch in dm_channels}
    results = []
    for user in users:
        dm_id = dm_by_user.get(user["id"])
        if dm_id:
            results.append({"channel_id": dm_id, "label": f"{user['real_name']} (DM)"})
    for ch in channels:
        results.append({"channel_id": ch["id"], "label": f"#{ch['name']} (channel)"})
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Slack Huddle & Message Analytics")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, fetch everything fresh (don't save)")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached data before running")
    return parser.parse_args(argv)


def fetch_with_cache(
    client: SlackClient,
    cache: CacheManager,
    channel_id: str,
    use_cache: bool,
) -> list[dict]:
    if not use_cache:
        print("  (cache disabled)")
        raw = client.fetch_messages(channel_id)
        return [CacheManager.trim_message(m) for m in raw]

    cached = cache.load(channel_id)
    if cached is not None:
        last_ts = cached["last_ts"]
        print(f"  Cache found: {len(cached['messages']):,} messages up to {last_ts}")
        print("  Fetching new messages...")
        new_raw = client.fetch_messages(channel_id, oldest=last_ts)
        # conversations.history with oldest returns messages with ts > oldest,
        # but may include the boundary message. Deduplicate by ts.
        existing_ts = {m["ts"] for m in cached["messages"]}
        new_msgs = [CacheManager.trim_message(m) for m in new_raw if m.get("ts") not in existing_ts]
        if new_msgs:
            cache.append(channel_id, new_msgs, last_ts=new_msgs[0]["ts"])
            print(f"  Added {len(new_msgs):,} new messages to cache")
        else:
            print("  Cache is up to date")
        updated = cache.load(channel_id)
        return updated["messages"]
    else:
        print("  No cache found, fetching all messages (this may take a while)...")
        raw = client.fetch_messages(channel_id)
        trimmed = [CacheManager.trim_message(m) for m in raw]
        if trimmed:
            # conversations.history returns newest first, so first element has highest ts
            latest_ts = trimmed[0]["ts"]
            cache.save(channel_id, trimmed, last_ts=latest_ts)
            print(f"  Cached {len(trimmed):,} messages")
        return trimmed


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    load_dotenv()
    token = os.getenv("SLACK_USER_TOKEN")
    user_id = os.getenv("SLACK_USER_ID")

    if not token or not user_id:
        print("Missing configuration. Create a .env file with:")
        print("  SLACK_USER_TOKEN=xoxp-your-token-here")
        print("  SLACK_USER_ID=U_YOUR_USER_ID")
        print()
        print("To get these values:")
        print("  1. Go to https://api.slack.com/apps and create a new app")
        print("  2. Under OAuth & Permissions, add these User Token Scopes:")
        print("     channels:history, groups:history, im:history,")
        print("     users:read, channels:read, groups:read, im:read")
        print("  3. Install the app to your workspace")
        print("  4. Copy the User OAuth Token (starts with xoxp-)")
        print("  5. Find your User ID in Slack (Profile > ... > Copy member ID)")
        sys.exit(1)

    client = SlackClient(token=token, user_id=user_id)
    cache = CacheManager()

    if args.clear_cache:
        cache.clear_all()
        print("Cache cleared.")

    query = input("\nSearch for a person or channel: ").strip()
    if not query:
        print("No search query entered.")
        sys.exit(1)

    print(f"\nSearching for '{query}'...")
    users = client.search_users(query)
    dm_channels = client.list_dm_channels()
    channels = client.search_channels(query)

    results = build_search_results(users, dm_channels, channels)
    if not results:
        print("No matches found.")
        sys.exit(1)

    print()
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['label']}")
    print()

    choice = input(f"Select [1-{len(results)}]: ").strip()
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(results):
            raise ValueError
    except ValueError:
        print("Invalid selection.")
        sys.exit(1)

    selected = results[idx]

    # Analytics type selection
    print(f"\nWhat would you like to analyze for {selected['label']}?")
    print("  1. Huddle Time")
    print("  2. Message Analytics")
    print("  3. Both")
    print()
    analytics_choice = input("Select [1-3]: ").strip()

    print(f"\nFetching data from {selected['label']}...")
    use_cache = not args.no_cache
    messages = fetch_with_cache(client, cache, selected["channel_id"], use_cache)

    if analytics_choice == "2":
        stats = compute_message_stats(messages, user_id)
        print(format_message_report(stats, selected["label"]))
    elif analytics_choice == "3":
        huddles = extract_huddles(messages)
        h_stats = compute_stats(huddles, user_id)
        print(format_report(h_stats, selected["label"], client.resolve_user_name))
        m_stats = compute_message_stats(messages, user_id)
        print(format_message_report(m_stats, selected["label"]))
    else:
        huddles = extract_huddles(messages)
        stats = compute_stats(huddles, user_id)
        print(format_report(stats, selected["label"], client.resolve_user_name))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: add cache integration, analytics menu, --no-cache and --clear-cache flags"
```

---

### Task 6: Integration Test & Cleanup

**Files:**
- All test files

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 2: Verify CLI flags work**

Run: `python -m src.main --help`
Expected output includes `--no-cache` and `--clear-cache` options.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "chore: integration test cleanup"
```
