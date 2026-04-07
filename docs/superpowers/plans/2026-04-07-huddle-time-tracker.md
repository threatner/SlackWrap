# Huddle Time Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that fetches Slack huddle history for a selected channel/DM and reports total time spent in huddles.

**Architecture:** Three-module Python CLI — `slack_client.py` handles all Slack API interaction with pagination and rate limiting, `report.py` computes stats and formats output, `main.py` orchestrates the interactive flow. Config via `.env` file with `python-dotenv`.

**Tech Stack:** Python 3.10+, `requests`, `python-dotenv`, `pytest`

---

## File Map

| File | Responsibility |
|---|---|
| `src/__init__.py` | Package marker |
| `src/slack_client.py` | Slack API wrapper: user search, channel listing, conversation history, user info resolution |
| `src/report.py` | Huddle data parsing, duration computation, stats aggregation, CLI formatting |
| `src/main.py` | Entry point: env loading, interactive prompts, orchestration |
| `tests/__init__.py` | Test package marker |
| `tests/test_slack_client.py` | Tests for API wrapper (mocked HTTP) |
| `tests/test_report.py` | Tests for parsing, stats, formatting (pure functions, no mocks) |
| `tests/test_main.py` | Tests for orchestration flow (mocked dependencies) |
| `.env.example` | Template for required env vars |
| `.gitignore` | Ignore `.env`, `__pycache__`, `.pytest_cache`, `*.pyc` |
| `requirements.txt` | Runtime + dev dependencies |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
```

- [ ] **Step 2: Create `.env.example`**

```
SLACK_USER_TOKEN=xoxp-your-token-here
SLACK_USER_ID=U_YOUR_USER_ID
```

- [ ] **Step 3: Create `requirements.txt`**

```
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 4: Create empty `src/__init__.py` and `tests/__init__.py`**

Both files are empty — just package markers.

- [ ] **Step 5: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully.

- [ ] **Step 6: Commit**

```bash
git add .gitignore .env.example requirements.txt src/__init__.py tests/__init__.py
git commit -m "chore: scaffold project with dependencies and config template"
```

---

### Task 2: Slack Client — User Search

**Files:**
- Create: `src/slack_client.py`
- Create: `tests/test_slack_client.py`

- [ ] **Step 1: Write failing test for `search_users`**

```python
# tests/test_slack_client.py
from unittest.mock import patch, MagicMock
from src.slack_client import SlackClient


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestSearchUsers:
    def test_search_users_filters_by_name(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        users_response = {
            "ok": True,
            "members": [
                {"id": "U001", "name": "john.smith", "real_name": "John Smith", "deleted": False, "is_bot": False},
                {"id": "U002", "name": "jane.doe", "real_name": "Jane Doe", "deleted": False, "is_bot": False},
                {"id": "U003", "name": "johnny.b", "real_name": "Johnny B", "deleted": False, "is_bot": False},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(users_response)):
            results = client.search_users("john")

        assert len(results) == 2
        assert results[0]["id"] == "U001"
        assert results[1]["id"] == "U003"

    def test_search_users_excludes_bots_and_deleted(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        users_response = {
            "ok": True,
            "members": [
                {"id": "U001", "name": "john.smith", "real_name": "John Smith", "deleted": False, "is_bot": False},
                {"id": "U002", "name": "john.bot", "real_name": "John Bot", "deleted": False, "is_bot": True},
                {"id": "U003", "name": "john.gone", "real_name": "John Gone", "deleted": True, "is_bot": False},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(users_response)):
            results = client.search_users("john")

        assert len(results) == 1
        assert results[0]["id"] == "U001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_slack_client.py -v`
Expected: FAIL — `ImportError: cannot import name 'SlackClient'`

- [ ] **Step 3: Implement `SlackClient` with `search_users`**

```python
# src/slack_client.py
import time
import requests

API_BASE = "https://slack.com/api"
RATE_LIMIT_DELAY = 1.2  # seconds between paginated requests


class SlackClient:
    def __init__(self, token: str, user_id: str):
        self.token = token
        self.user_id = user_id
        self.headers = {"Authorization": f"Bearer {token}"}
        self._user_cache: dict[str, str] = {}

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        resp = requests.get(f"{API_BASE}/{endpoint}", headers=self.headers, params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")
        return data

    def search_users(self, query: str) -> list[dict]:
        query_lower = query.lower()
        matches = []
        cursor = ""
        while True:
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("users.list", params)
            for member in data.get("members", []):
                if member.get("deleted") or member.get("is_bot"):
                    continue
                name = member.get("real_name", "").lower()
                username = member.get("name", "").lower()
                if query_lower in name or query_lower in username:
                    matches.append(member)
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            time.sleep(RATE_LIMIT_DELAY)
        return matches
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_slack_client.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slack_client.py tests/test_slack_client.py
git commit -m "feat: add SlackClient with user search"
```

---

### Task 3: Slack Client — Channel Listing & DM Resolution

**Files:**
- Modify: `src/slack_client.py`
- Modify: `tests/test_slack_client.py`

- [ ] **Step 1: Write failing tests for `list_dm_channels` and `search_channels`**

Add to `tests/test_slack_client.py`:

```python
class TestListDmChannels:
    def test_returns_dm_channels(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        convos_response = {
            "ok": True,
            "channels": [
                {"id": "D001", "user": "U001"},
                {"id": "D002", "user": "U002"},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(convos_response)):
            results = client.list_dm_channels()

        assert len(results) == 2
        assert results[0]["id"] == "D001"
        assert results[0]["user"] == "U001"


class TestSearchChannels:
    def test_search_channels_filters_by_name(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        convos_response = {
            "ok": True,
            "channels": [
                {"id": "C001", "name": "john-project", "is_im": False, "is_mpim": False},
                {"id": "C002", "name": "engineering", "is_im": False, "is_mpim": False},
                {"id": "C003", "name": "john-standup", "is_im": False, "is_mpim": False},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(convos_response)):
            results = client.search_channels("john")

        assert len(results) == 2
        assert results[0]["id"] == "C001"
        assert results[1]["id"] == "C003"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_slack_client.py -v`
Expected: FAIL — `AttributeError: 'SlackClient' object has no attribute 'list_dm_channels'`

- [ ] **Step 3: Implement `list_dm_channels` and `search_channels`**

Add to `src/slack_client.py` inside `SlackClient`:

```python
    def list_dm_channels(self) -> list[dict]:
        channels = []
        cursor = ""
        while True:
            params = {"types": "im", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.list", params)
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            time.sleep(RATE_LIMIT_DELAY)
        return channels

    def search_channels(self, query: str) -> list[dict]:
        query_lower = query.lower()
        matches = []
        cursor = ""
        while True:
            params = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.list", params)
            for ch in data.get("channels", []):
                if query_lower in ch.get("name", "").lower():
                    matches.append(ch)
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            time.sleep(RATE_LIMIT_DELAY)
        return matches
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_slack_client.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slack_client.py tests/test_slack_client.py
git commit -m "feat: add DM channel listing and channel search"
```

---

### Task 4: Slack Client — Fetch Huddles from Conversation History

**Files:**
- Modify: `src/slack_client.py`
- Modify: `tests/test_slack_client.py`

- [ ] **Step 1: Write failing test for `fetch_huddles`**

Add to `tests/test_slack_client.py`:

```python
class TestFetchHuddles:
    def test_extracts_huddle_thread_messages(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {"type": "message", "text": "hello"},
                {
                    "type": "message",
                    "subtype": "huddle_thread",
                    "room": {
                        "date_start": 1700000000,
                        "date_end": 1700003600,
                        "has_ended": True,
                        "participant_history": ["U_ME", "U001"],
                        "created_by": "U_ME",
                    },
                },
                {"type": "message", "text": "world"},
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(history_response)):
            huddles = client.fetch_huddles("C12345")

        assert len(huddles) == 1
        assert huddles[0]["room"]["date_start"] == 1700000000

    def test_skips_ongoing_huddles(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "subtype": "huddle_thread",
                    "room": {
                        "date_start": 1700000000,
                        "date_end": 0,
                        "has_ended": False,
                        "participant_history": ["U_ME", "U001"],
                        "created_by": "U_ME",
                    },
                },
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(history_response)):
            huddles = client.fetch_huddles("C12345")

        assert len(huddles) == 0

    def test_paginates_through_history(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        page1 = {
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "subtype": "huddle_thread",
                    "room": {
                        "date_start": 1700000000,
                        "date_end": 1700003600,
                        "has_ended": True,
                        "participant_history": ["U_ME", "U001"],
                        "created_by": "U_ME",
                    },
                },
            ],
            "has_more": True,
            "response_metadata": {"next_cursor": "cursor_abc"},
        }
        page2 = {
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "subtype": "huddle_thread",
                    "room": {
                        "date_start": 1700010000,
                        "date_end": 1700011800,
                        "has_ended": True,
                        "participant_history": ["U_ME", "U001"],
                        "created_by": "U001",
                    },
                },
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", side_effect=[_mock_response(page1), _mock_response(page2)]):
            with patch("src.slack_client.time.sleep"):
                huddles = client.fetch_huddles("C12345")

        assert len(huddles) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_slack_client.py::TestFetchHuddles -v`
Expected: FAIL — `AttributeError: 'SlackClient' object has no attribute 'fetch_huddles'`

- [ ] **Step 3: Implement `fetch_huddles`**

Add to `src/slack_client.py` inside `SlackClient`:

```python
    def fetch_huddles(self, channel_id: str) -> list[dict]:
        huddles = []
        cursor = ""
        while True:
            params = {"channel": channel_id, "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.history", params)
            for msg in data.get("messages", []):
                if msg.get("subtype") != "huddle_thread":
                    continue
                room = msg.get("room", {})
                if not room.get("has_ended"):
                    continue
                huddles.append(msg)
            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            time.sleep(RATE_LIMIT_DELAY)
        return huddles
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_slack_client.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slack_client.py tests/test_slack_client.py
git commit -m "feat: add huddle fetching from conversation history"
```

---

### Task 5: Slack Client — Resolve User Display Names

**Files:**
- Modify: `src/slack_client.py`
- Modify: `tests/test_slack_client.py`

- [ ] **Step 1: Write failing test for `resolve_user_name`**

Add to `tests/test_slack_client.py`:

```python
class TestResolveUserName:
    def test_returns_display_name(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        user_response = {
            "ok": True,
            "user": {"id": "U001", "real_name": "John Smith"},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(user_response)):
            name = client.resolve_user_name("U001")

        assert name == "John Smith"

    def test_caches_results(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        user_response = {
            "ok": True,
            "user": {"id": "U001", "real_name": "John Smith"},
        }
        mock_get = MagicMock(return_value=_mock_response(user_response))
        with patch("src.slack_client.requests.get", mock_get):
            client.resolve_user_name("U001")
            client.resolve_user_name("U001")

        assert mock_get.call_count == 1

    def test_returns_you_for_own_user_id(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        name = client.resolve_user_name("U_ME")
        assert name == "You"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_slack_client.py::TestResolveUserName -v`
Expected: FAIL — `AttributeError: 'SlackClient' object has no attribute 'resolve_user_name'`

- [ ] **Step 3: Implement `resolve_user_name`**

Add to `src/slack_client.py` inside `SlackClient`:

```python
    def resolve_user_name(self, user_id: str) -> str:
        if user_id == self.user_id:
            return "You"
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        data = self._get("users.info", {"user": user_id})
        name = data.get("user", {}).get("real_name", user_id)
        self._user_cache[user_id] = name
        return name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_slack_client.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slack_client.py tests/test_slack_client.py
git commit -m "feat: add user name resolution with caching"
```

---

### Task 6: Report — Duration Computation & Stats

**Files:**
- Create: `src/report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Write failing tests for `format_duration` and `compute_stats`**

```python
# tests/test_report.py
from src.report import format_duration, compute_stats


class TestFormatDuration:
    def test_minutes_only(self):
        assert format_duration(900) == "0h 15m"

    def test_hours_and_minutes(self):
        assert format_duration(3900) == "1h 05m"

    def test_zero(self):
        assert format_duration(0) == "0h 00m"

    def test_exact_hour(self):
        assert format_duration(7200) == "2h 00m"


class TestComputeStats:
    def test_computes_aggregate_stats(self):
        huddles = [
            {"room": {"date_start": 1000, "date_end": 2000, "created_by": "U001", "participant_history": ["U_ME", "U001"]}},
            {"room": {"date_start": 3000, "date_end": 6600, "created_by": "U_ME", "participant_history": ["U_ME", "U001"]}},
            {"room": {"date_start": 7000, "date_end": 8800, "created_by": "U001", "participant_history": ["U_ME", "U001"]}},
        ]
        stats = compute_stats(huddles, "U_ME")

        assert stats["total_huddles"] == 3
        assert stats["total_seconds"] == (1000 + 3600 + 1800)
        assert stats["avg_seconds"] == (1000 + 3600 + 1800) // 3
        assert stats["longest_seconds"] == 3600
        assert stats["shortest_seconds"] == 1000

    def test_filters_huddles_without_user(self):
        huddles = [
            {"room": {"date_start": 1000, "date_end": 2000, "created_by": "U001", "participant_history": ["U001", "U002"]}},
            {"room": {"date_start": 3000, "date_end": 6600, "created_by": "U_ME", "participant_history": ["U_ME", "U001"]}},
        ]
        stats = compute_stats(huddles, "U_ME")

        assert stats["total_huddles"] == 1
        assert stats["total_seconds"] == 3600

    def test_empty_huddles(self):
        stats = compute_stats([], "U_ME")
        assert stats["total_huddles"] == 0
        assert stats["total_seconds"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -v`
Expected: FAIL — `ImportError: cannot import name 'format_duration'`

- [ ] **Step 3: Implement `format_duration` and `compute_stats`**

```python
# src/report.py
from datetime import datetime, timezone


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes:02d}m"


def compute_stats(huddles: list[dict], user_id: str) -> dict:
    user_huddles = [
        h for h in huddles
        if user_id in h["room"]["participant_history"]
    ]
    if not user_huddles:
        return {
            "total_huddles": 0,
            "total_seconds": 0,
            "avg_seconds": 0,
            "longest_seconds": 0,
            "shortest_seconds": 0,
            "huddles": [],
        }
    durations = [
        h["room"]["date_end"] - h["room"]["date_start"]
        for h in user_huddles
    ]
    return {
        "total_huddles": len(user_huddles),
        "total_seconds": sum(durations),
        "avg_seconds": sum(durations) // len(durations),
        "longest_seconds": max(durations),
        "shortest_seconds": min(durations),
        "huddles": user_huddles,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/report.py tests/test_report.py
git commit -m "feat: add duration formatting and stats computation"
```

---

### Task 7: Report — CLI Formatting

**Files:**
- Modify: `src/report.py`
- Modify: `tests/test_report.py`

- [ ] **Step 1: Write failing test for `format_report`**

Add to `tests/test_report.py`:

```python
from src.report import format_duration, compute_stats, format_report


class TestFormatReport:
    def test_formats_report_with_huddles(self):
        huddles = [
            {"room": {"date_start": 1700000000, "date_end": 1700001920, "created_by": "U001", "participant_history": ["U_ME", "U001"]}},
            {"room": {"date_start": 1700100000, "date_end": 1700103600, "created_by": "U_ME", "participant_history": ["U_ME", "U001"]}},
        ]
        stats = compute_stats(huddles, "U_ME")

        def mock_resolve(uid):
            return {"U_ME": "You", "U001": "Alice"}.get(uid, uid)

        output = format_report(stats, "DM with Alice", mock_resolve)

        assert "Huddle Time Report" in output
        assert "DM with Alice" in output
        assert "Total huddles: 2" in output
        assert "Alice" in output
        assert "You" in output
        assert "Total time:" in output
        assert "Avg per huddle:" in output
        assert "Longest huddle:" in output
        assert "Shortest huddle:" in output

    def test_formats_empty_report(self):
        stats = compute_stats([], "U_ME")

        output = format_report(stats, "DM with Alice", lambda uid: uid)

        assert "No huddles found" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py::TestFormatReport -v`
Expected: FAIL — `ImportError: cannot import name 'format_report'`

- [ ] **Step 3: Implement `format_report`**

Add to `src/report.py`:

```python
from typing import Callable


def format_report(stats: dict, channel_label: str, resolve_name: Callable[[str], str]) -> str:
    if stats["total_huddles"] == 0:
        return f"\nHuddle Time Report\n==================\nChannel: {channel_label}\n\nNo huddles found.\n"

    lines = []
    lines.append("")
    lines.append("Huddle Time Report")
    lines.append("=" * 40)
    lines.append(f"Channel: {channel_label}")

    huddles = stats["huddles"]
    first_date = datetime.fromtimestamp(huddles[-1]["room"]["date_start"], tz=timezone.utc).astimezone()
    last_date = datetime.fromtimestamp(huddles[0]["room"]["date_start"], tz=timezone.utc).astimezone()
    lines.append(f"Period:  {first_date.strftime('%Y-%m-%d')} -> {last_date.strftime('%Y-%m-%d')}")
    lines.append(f"Total huddles: {stats['total_huddles']}")
    lines.append("")
    lines.append(f"{'Date':<13}{'Started By':<18}{'Duration'}")
    lines.append("-" * 40)

    sorted_huddles = sorted(huddles, key=lambda h: h["room"]["date_start"])
    for h in sorted_huddles:
        room = h["room"]
        dt = datetime.fromtimestamp(room["date_start"], tz=timezone.utc).astimezone()
        date_str = dt.strftime("%Y-%m-%d")
        started_by = resolve_name(room["created_by"])
        duration = format_duration(room["date_end"] - room["date_start"])
        lines.append(f"{date_str:<13}{started_by:<18}{duration}")

    lines.append("")
    lines.append("Summary")
    lines.append("-" * 40)
    lines.append(f"Total time:      {format_duration(stats['total_seconds'])}")
    lines.append(f"Avg per huddle:  {format_duration(stats['avg_seconds'])}")
    lines.append(f"Longest huddle:  {format_duration(stats['longest_seconds'])}")
    lines.append(f"Shortest huddle: {format_duration(stats['shortest_seconds'])}")
    lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/report.py tests/test_report.py
git commit -m "feat: add CLI report formatting"
```

---

### Task 8: Main — Interactive Flow & Orchestration

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing test for `build_search_results`**

```python
# tests/test_main.py
from src.main import build_search_results


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_search_results'`

- [ ] **Step 3: Implement `build_search_results` and `main`**

```python
# src/main.py
import os
import sys
from dotenv import load_dotenv
from src.slack_client import SlackClient
from src.report import compute_stats, format_report


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


def main():
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
    print(f"\nFetching huddles from {selected['label']}...")
    huddles = client.fetch_huddles(selected["channel_id"])

    stats = compute_stats(huddles, user_id)
    output = format_report(stats, selected["label"], client.resolve_user_name)
    print(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: add interactive main flow with channel selection"
```

---

### Task 9: End-to-End Verification & README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 2: Create README**

```markdown
# Huddle Time Tracker

A Python CLI tool that shows how much time you've spent in Slack huddles with a colleague.

## Setup

### 1. Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**
2. Choose **From scratch**, name it (e.g., "Huddle Tracker"), and select your workspace
3. Go to **OAuth & Permissions**
4. Under **User Token Scopes**, add:
   - `channels:history`
   - `groups:history`
   - `im:history`
   - `users:read`
   - `channels:read`
   - `groups:read`
   - `im:read`
5. Click **Install to Workspace** and authorize
6. Copy the **User OAuth Token** (starts with `xoxp-`)

### 2. Find Your Slack User ID

1. Open Slack, click your profile picture
2. Click **Profile**
3. Click the **...** menu and select **Copy member ID**

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in your token and user ID.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

```bash
python -m src.main
```

You'll be prompted to search for a person or channel, then the tool will fetch all huddles and display a time report.

## Example Output

```
Huddle Time Report
========================================
Channel: John Smith (DM)
Period:  2025-01-15 -> 2026-04-07
Total huddles: 47

Date         Started By        Duration
----------------------------------------
2025-01-15   You               0h 32m
2025-01-18   John Smith        1h 05m
...

Summary
----------------------------------------
Total time:      38h 42m
Avg per huddle:  0h 49m
Longest huddle:  3h 12m
Shortest huddle: 0h 04m
```
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage guide"
```

- [ ] **Step 4: Manual test with real Slack token**

Run: `python -m src.main`
- Verify the search prompt appears
- Search for a known colleague
- Verify huddle data is fetched and report is displayed
