# SlackWrap v2 — Plan 2: Analytics Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a general-purpose query layer over the SQLite database that powers every view — Wrapped story, explorer, deep dives, and chat. All v1 analytics are preserved, new v2 analytics are added, and everything is queryable via a Filters dataclass.

**Architecture:** The analytics engine is a Python module with a central `AnalyticsEngine` class that accepts a `Database` instance and a `Filters` dataclass. Methods return structured dataclasses (not flat dicts like v1). Each analytics domain (volume, response time, streaks, etc.) is a focused method. A `compute_rollups()` method populates the weekly_stats and monthly_stats tables for fast pre-computed lookups.

**Tech Stack:** Python 3.10+, sqlite3 (via Database from Plan 1), dataclasses, re (for text cleaning)

**Spec:** `docs/superpowers/specs/2026-04-09-slackwrap-v2-design.md` (Analytics Engine section)

**Depends on:** Plan 1 (Data Layer) — all code in `src/slackwrap/` from the `v2/data-layer` branch.

---

## File Structure

```
src/slackwrap/
  analytics/
    __init__.py          # Exports AnalyticsEngine, Filters, all result types
    engine.py            # AnalyticsEngine class — central query coordinator
    filters.py           # Filters dataclass and SQL WHERE clause builder
    types.py             # All result dataclasses (VolumeStats, HuddleStats, etc.)
    volume.py            # Message volume, per-user split, busiest day, active days
    huddles.py           # Huddle stats, who starts, duration analysis
    response_time.py     # Turn-based response times, by hour, trends
    threads.py           # Thread breakdown, reply depth
    communication.py     # Word counts, top words, emoji, reactions, links/files
    streaks.py           # Conversation streaks, gaps, milestones
    trends.py            # 30-day rolling, YoY, monthly rank
    heatmap.py           # Hour x day-of-week heatmap, peak collaboration windows
    relationship.py      # Reciprocity index, emoji diversity, shared channel distribution
    rollups.py           # Compute and store weekly_stats / monthly_stats
    text_processing.py   # Regex helpers for word counting, emoji extraction (ported from v1)
tests/
  test_analytics_filters.py
  test_analytics_volume.py
  test_analytics_huddles.py
  test_analytics_response_time.py
  test_analytics_threads.py
  test_analytics_communication.py
  test_analytics_streaks.py
  test_analytics_trends.py
  test_analytics_heatmap.py
  test_analytics_relationship.py
  test_analytics_rollups.py
  test_analytics_engine.py
```

Each analytics module is a pure function that takes a `Database` and `Filters` and returns a typed result. The `AnalyticsEngine` class is a thin coordinator that delegates to these modules. This keeps each file focused and independently testable.

---

### Task 1: Filters and SQL Builder

**Files:**
- Create: `src/slackwrap/analytics/__init__.py`
- Create: `src/slackwrap/analytics/filters.py`
- Create: `tests/test_analytics_filters.py`

- [ ] **Step 1: Create package init**

```python
# src/slackwrap/analytics/__init__.py
```

Empty file.

- [ ] **Step 2: Write failing tests**

```python
# tests/test_analytics_filters.py
from __future__ import annotations
from datetime import date


def test_empty_filters_produce_no_where_clause():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters()
    clause, params = build_where(f)
    assert clause == ""
    assert params == []


def test_single_user_filter():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters(user_id=1)
    clause, params = build_where(f)
    assert "m.user_id = ?" in clause
    assert params == [1]


def test_date_range_filter():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters(date_from=date(2025, 1, 1), date_to=date(2025, 6, 30))
    clause, params = build_where(f)
    assert "m.created_at >= ?" in clause
    assert "m.created_at < ?" in clause
    assert len(params) == 2


def test_channel_filter():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters(channel_id=5)
    clause, params = build_where(f)
    assert "m.channel_id = ?" in clause
    assert params == [5]


def test_combined_filters():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters(user_id=1, channel_id=5, in_thread=True)
    clause, params = build_where(f)
    assert "m.user_id = ?" in clause
    assert "m.channel_id = ?" in clause
    assert "m.thread_ts IS NOT NULL AND m.thread_ts != m.slack_ts" in clause
    assert 1 in params
    assert 5 in params


def test_day_of_week_filter():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters(day_of_week="Monday")
    clause, params = build_where(f)
    # SQLite strftime('%w') returns 0=Sunday, 1=Monday
    assert "strftime('%w'" in clause


def test_hour_filter():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters(hour=14)
    clause, params = build_where(f)
    assert "strftime('%H'" in clause
    assert 14 in params or "14" in params


def test_has_reactions_filter():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters(has_reactions=True)
    clause, params = build_where(f)
    assert "EXISTS" in clause or "reactions" in clause.lower()


def test_relationship_key_filter():
    from slackwrap.analytics.filters import Filters, build_where

    f = Filters(relationship_key="1:2")
    clause, params = build_where(f)
    assert "m.user_id IN" in clause
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_filters.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement Filters and build_where**

```python
# src/slackwrap/analytics/filters.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone


# SQLite strftime('%w') mapping: 0=Sunday, 1=Monday, ..., 6=Saturday
DAY_TO_WEEKDAY_NUM = {
    "Sunday": "0", "Monday": "1", "Tuesday": "2", "Wednesday": "3",
    "Thursday": "4", "Friday": "5", "Saturday": "6",
}


@dataclass
class Filters:
    relationship_key: str | None = None  # "user_id_1:user_id_2"
    user_id: int | None = None
    channel_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    day_of_week: str | None = None
    hour: int | None = None
    subtype: str | None = None
    has_reactions: bool | None = None
    has_files: bool | None = None
    in_thread: bool | None = None


def build_where(filters: Filters, table_alias: str = "m") -> tuple[str, list]:
    """Build a SQL WHERE clause from Filters. Returns (clause_string, params_list).

    If no filters are active, returns ("", []).
    Otherwise returns ("WHERE ...", [param1, param2, ...]).
    The clause references columns on the given table alias (default 'm' for messages).
    """
    conditions: list[str] = []
    params: list = []
    a = table_alias

    if filters.relationship_key:
        parts = filters.relationship_key.split(":")
        if len(parts) == 2:
            uid1, uid2 = int(parts[0]), int(parts[1])
            conditions.append(f"{a}.user_id IN (?, ?)")
            params.extend([uid1, uid2])

    if filters.user_id is not None:
        conditions.append(f"{a}.user_id = ?")
        params.append(filters.user_id)

    if filters.channel_id is not None:
        conditions.append(f"{a}.channel_id = ?")
        params.append(filters.channel_id)

    if filters.date_from is not None:
        ts = datetime(filters.date_from.year, filters.date_from.month,
                      filters.date_from.day, tzinfo=timezone.utc).timestamp()
        conditions.append(f"{a}.created_at >= ?")
        params.append(ts)

    if filters.date_to is not None:
        # date_to is inclusive: include the full day
        next_day = datetime(filters.date_to.year, filters.date_to.month,
                           filters.date_to.day, tzinfo=timezone.utc).timestamp() + 86400
        conditions.append(f"{a}.created_at < ?")
        params.append(next_day)

    if filters.day_of_week is not None:
        weekday_num = DAY_TO_WEEKDAY_NUM.get(filters.day_of_week)
        if weekday_num is not None:
            conditions.append(f"strftime('%w', {a}.created_at, 'unixepoch') = ?")
            params.append(weekday_num)

    if filters.hour is not None:
        conditions.append(f"CAST(strftime('%H', {a}.created_at, 'unixepoch', 'localtime') AS INTEGER) = ?")
        params.append(filters.hour)

    if filters.subtype is not None:
        conditions.append(f"{a}.subtype = ?")
        params.append(filters.subtype)

    if filters.has_reactions is True:
        conditions.append(f"EXISTS (SELECT 1 FROM reactions r WHERE r.message_id = {a}.id)")

    if filters.has_files is True:
        conditions.append(f"{a}.files_count > 0")

    if filters.in_thread is True:
        conditions.append(f"{a}.thread_ts IS NOT NULL AND {a}.thread_ts != {a}.slack_ts")
    elif filters.in_thread is False:
        conditions.append(f"({a}.thread_ts IS NULL OR {a}.thread_ts = {a}.slack_ts)")

    if not conditions:
        return "", []
    return "WHERE " + " AND ".join(conditions), params
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_filters.py -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/slackwrap/analytics/__init__.py src/slackwrap/analytics/filters.py tests/test_analytics_filters.py
git commit -m "feat(v2): add Filters dataclass and SQL WHERE clause builder"
```

---

### Task 2: Result Types

**Files:**
- Create: `src/slackwrap/analytics/types.py`
- Create: `tests/test_analytics_types.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_types.py
from __future__ import annotations


def test_volume_stats_creation():
    from slackwrap.analytics.types import VolumeStats

    vs = VolumeStats(
        total_messages=1000, you_count=500, them_count=500,
        you_pct=50.0, them_pct=50.0, per_week=63.0,
        busiest_day_date="2025-03-14", busiest_day_count=87,
        active_days=240, total_days=365,
        weekday_count=800, weekend_count=200,
        messages_per_active_day=4.2,
        monthly_volumes={"2025-01": 120, "2025-02": 150},
        monthly_rank=[("2025-02", 150, 1), ("2025-01", 120, 2)],
    )
    assert vs.total_messages == 1000
    assert vs.active_days == 240


def test_huddle_stats_creation():
    from slackwrap.analytics.types import HuddleStats

    hs = HuddleStats(
        total_huddles=50, total_seconds=180000,
        avg_seconds=3600, median_seconds=3000,
        longest_seconds=7200, shortest_seconds=120,
        started_by_you=30, started_by_them=20,
        weekday_breakdown={"Monday": 10},
        per_week=2.5, per_month=10.0,
        huddle_to_message_ratio=30.0,
    )
    assert hs.total_huddles == 50
    assert hs.huddle_to_message_ratio == 30.0


def test_response_time_stats_creation():
    from slackwrap.analytics.types import ResponseTimeStats

    rts = ResponseTimeStats(
        your_median=240, your_avg=300,
        their_median=180, their_avg=250,
        fastest_hour=10, fastest_hour_median=60,
        slowest_hour=23, slowest_hour_median=1800,
        by_hour={10: 60, 14: 120, 23: 1800},
        monthly_trend={"2025-01": 300, "2025-02": 250},
    )
    assert rts.your_median == 240
    assert rts.fastest_hour == 10


def test_streak_stats_creation():
    from slackwrap.analytics.types import StreakStats

    ss = StreakStats(
        longest_streak_days=47,
        longest_streak_start=1700000000.0,
        longest_streak_end=1704000000.0,
        current_streak_days=12,
        longest_gap_seconds=1555200,
        longest_gap_start=1700000000.0,
        longest_gap_end=1701555200.0,
        milestones={"1000th message": "2025-03-03"},
    )
    assert ss.longest_streak_days == 47
    assert "1000th message" in ss.milestones


def test_communication_stats_creation():
    from slackwrap.analytics.types import CommunicationStats

    cs = CommunicationStats(
        your_avg_words=11.2, their_avg_words=8.7,
        your_top_words=[("looks", 142), ("review", 98)],
        their_top_words=[("yeah", 203)],
        your_emoji_total=50, their_emoji_total=30,
        your_top_emojis=[("rocket", 20)],
        their_top_emojis=[("thumbsup", 15)],
        your_reactions_given=100, their_reactions_given=80,
        top_reactions=[("thumbsup", 50)],
        your_links=34, their_links=20,
        your_files=12, their_files=8,
        message_length_distribution={"short": 400, "medium": 350, "long": 250},
        emoji_diversity_you=25, emoji_diversity_them=10,
    )
    assert cs.your_avg_words == 11.2
    assert cs.emoji_diversity_you == 25


def test_thread_stats_creation():
    from slackwrap.analytics.types import ThreadStats

    ts = ThreadStats(
        total_messages=5000, top_level=4000, in_threads=1000,
        thread_pct=20.0,
        threads_started_by_you=62, threads_started_by_them=71,
        deepest_thread=15, avg_thread_depth=3.2,
    )
    assert ts.thread_pct == 20.0
    assert ts.deepest_thread == 15


def test_trend_stats_creation():
    from slackwrap.analytics.types import TrendStats

    ts = TrendStats(
        last_30d_count=312, prev_30d_count=263,
        pct_change_30d=18.6,
        current_month="2025-04", current_month_count=41,
        yoy_month="2024-04", yoy_count=35,
        yoy_pct_change=5.2,
    )
    assert ts.pct_change_30d == 18.6


def test_heatmap_result_creation():
    from slackwrap.analytics.types import HeatmapResult

    hr = HeatmapResult(
        data={0: {0: 5, 1: 10}, 1: {0: 3}},
        x_labels=["Mon", "Tue"],
        y_labels=["00:00", "01:00"],
    )
    assert hr.data[0][1] == 10


def test_relationship_stats_creation():
    from slackwrap.analytics.types import RelationshipStats

    rs = RelationshipStats(
        reciprocity_index=0.85,
        conversation_initiations_you=100,
        conversation_initiations_them=80,
        first_message={"ts": 1700000000.0, "text": "hello", "user_id": 1},
        last_message={"ts": 1710000000.0, "text": "bye", "user_id": 2},
        pinned_highlights=[],
        shared_channel_distribution={"general": 500, "random": 200},
    )
    assert rs.reciprocity_index == 0.85


def test_query_result_creation():
    from slackwrap.analytics.types import QueryResult

    qr = QueryResult(rows=[{"count": 100}], columns=["count"], row_count=1)
    assert qr.row_count == 1
    assert qr.rows[0]["count"] == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_types.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement result types**

```python
# src/slackwrap/analytics/types.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class VolumeStats:
    total_messages: int = 0
    you_count: int = 0
    them_count: int = 0
    you_pct: float = 0.0
    them_pct: float = 0.0
    per_week: float = 0.0
    busiest_day_date: str = ""
    busiest_day_count: int = 0
    active_days: int = 0
    total_days: int = 0
    weekday_count: int = 0
    weekend_count: int = 0
    messages_per_active_day: float = 0.0
    monthly_volumes: dict[str, int] = field(default_factory=dict)
    monthly_rank: list[tuple[str, int, int]] = field(default_factory=list)  # (month, count, rank)


@dataclass
class HuddleStats:
    total_huddles: int = 0
    total_seconds: int = 0
    avg_seconds: int = 0
    median_seconds: int = 0
    longest_seconds: int = 0
    shortest_seconds: int = 0
    started_by_you: int = 0
    started_by_them: int = 0
    weekday_breakdown: dict[str, int] = field(default_factory=dict)
    per_week: float = 0.0
    per_month: float = 0.0
    huddle_to_message_ratio: float = 0.0


@dataclass
class ResponseTimeStats:
    your_median: int = 0
    your_avg: int = 0
    their_median: int = 0
    their_avg: int = 0
    fastest_hour: int = 0
    fastest_hour_median: int = 0
    slowest_hour: int = 0
    slowest_hour_median: int = 0
    by_hour: dict[int, int] = field(default_factory=dict)
    monthly_trend: dict[str, int] = field(default_factory=dict)


@dataclass
class StreakStats:
    longest_streak_days: int = 0
    longest_streak_start: float = 0.0
    longest_streak_end: float = 0.0
    current_streak_days: int = 0
    longest_gap_seconds: int = 0
    longest_gap_start: float = 0.0
    longest_gap_end: float = 0.0
    milestones: dict[str, str] = field(default_factory=dict)  # label -> date string


@dataclass
class CommunicationStats:
    your_avg_words: float = 0.0
    their_avg_words: float = 0.0
    your_top_words: list[tuple[str, int]] = field(default_factory=list)
    their_top_words: list[tuple[str, int]] = field(default_factory=list)
    your_emoji_total: int = 0
    their_emoji_total: int = 0
    your_top_emojis: list[tuple[str, int]] = field(default_factory=list)
    their_top_emojis: list[tuple[str, int]] = field(default_factory=list)
    your_reactions_given: int = 0
    their_reactions_given: int = 0
    top_reactions: list[tuple[str, int]] = field(default_factory=list)
    your_links: int = 0
    their_links: int = 0
    your_files: int = 0
    their_files: int = 0
    message_length_distribution: dict[str, int] = field(default_factory=dict)
    emoji_diversity_you: int = 0
    emoji_diversity_them: int = 0


@dataclass
class ThreadStats:
    total_messages: int = 0
    top_level: int = 0
    in_threads: int = 0
    thread_pct: float = 0.0
    threads_started_by_you: int = 0
    threads_started_by_them: int = 0
    deepest_thread: int = 0
    avg_thread_depth: float = 0.0


@dataclass
class TrendStats:
    last_30d_count: int = 0
    prev_30d_count: int = 0
    pct_change_30d: float | None = None
    current_month: str = ""
    current_month_count: int = 0
    yoy_month: str = ""
    yoy_count: int | None = None
    yoy_pct_change: float | None = None


@dataclass
class HeatmapResult:
    data: dict[int, dict[int, int]] = field(default_factory=dict)  # x -> y -> count
    x_labels: list[str] = field(default_factory=list)
    y_labels: list[str] = field(default_factory=list)


@dataclass
class RelationshipStats:
    reciprocity_index: float = 0.0
    conversation_initiations_you: int = 0
    conversation_initiations_them: int = 0
    first_message: dict | None = None
    last_message: dict | None = None
    pinned_highlights: list[dict] = field(default_factory=list)
    shared_channel_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class QueryResult:
    rows: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_types.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/types.py tests/test_analytics_types.py
git commit -m "feat(v2): add analytics result types — VolumeStats, HuddleStats, ResponseTimeStats, etc."
```

---

### Task 3: Text Processing Helpers

Port the regex helpers from v1 (`src/message_analytics.py`) into the new analytics package.

**Files:**
- Create: `src/slackwrap/analytics/text_processing.py`
- Create: `tests/test_analytics_text_processing.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_text_processing.py
from __future__ import annotations


def test_clean_text_strips_code_blocks():
    from slackwrap.analytics.text_processing import clean_text_for_words

    text = "hello ```def foo(): pass``` world"
    result = clean_text_for_words(text)
    assert "def" not in result
    assert "hello" in result
    assert "world" in result


def test_clean_text_strips_mentions():
    from slackwrap.analytics.text_processing import clean_text_for_words

    text = "hey <@U12345> check this"
    result = clean_text_for_words(text)
    assert "U12345" not in result
    assert "hey" in result
    assert "check" in result


def test_clean_text_strips_links():
    from slackwrap.analytics.text_processing import clean_text_for_words

    text = "see <https://example.com|this link> here"
    result = clean_text_for_words(text)
    assert "https" not in result
    assert "see" in result


def test_clean_text_strips_emoji():
    from slackwrap.analytics.text_processing import clean_text_for_words

    text = "great job :thumbsup: :rocket:"
    result = clean_text_for_words(text)
    assert "thumbsup" not in result
    assert "great" in result


def test_count_words():
    from slackwrap.analytics.text_processing import count_words

    text = "The quick brown fox jumps"
    assert count_words(text) == 5


def test_count_words_strips_markup():
    from slackwrap.analytics.text_processing import count_words

    text = "hello ```code block``` world <@U123>"
    # After cleaning: "hello  world "
    assert count_words(text) == 2


def test_extract_emojis():
    from slackwrap.analytics.text_processing import extract_emojis

    text = "hey :rocket: nice :thumbsup: stuff"
    emojis = extract_emojis(text)
    assert emojis == ["rocket", "thumbsup"]


def test_extract_emojis_ignores_code_blocks():
    from slackwrap.analytics.text_processing import extract_emojis

    text = "```code :not_emoji:``` real :rocket:"
    emojis = extract_emojis(text)
    assert emojis == ["rocket"]


def test_count_links():
    from slackwrap.analytics.text_processing import count_links

    text = "see <https://example.com> and <https://other.com|link>"
    assert count_links(text) == 2


def test_top_words():
    from slackwrap.analytics.text_processing import top_words

    texts = ["the quick brown fox", "the lazy brown dog", "the quick red fox"]
    result = top_words(texts, n=3)
    # "the" is 2 letters, excluded (min 3). "quick" appears 2x, "brown" 2x, "fox" 2x
    words = [w for w, _ in result]
    assert "quick" in words
    assert "brown" in words
    assert "fox" in words


def test_classify_message_length():
    from slackwrap.analytics.text_processing import classify_message_length

    assert classify_message_length(2) == "short"      # <= 5 words
    assert classify_message_length(15) == "medium"     # 6-25 words
    assert classify_message_length(50) == "long"       # > 25 words
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_text_processing.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement text processing**

```python
# src/slackwrap/analytics/text_processing.py
from __future__ import annotations
import re
from collections import Counter

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]*)?>")
_LINK_RE = re.compile(r"<https?://[^>]+>")
_EMOJI_RE = re.compile(r":[a-zA-Z0-9_+-]+:")
_EMOJI_EXTRACT_RE = re.compile(r":([a-zA-Z0-9_+-]+):")
_WORD_TOKEN_RE = re.compile(r"[a-zA-Z]{3,}")


def clean_text_for_words(text: str) -> str:
    """Strip code blocks, inline code, mentions, links, and emoji from text."""
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _MENTION_RE.sub("", text)
    text = _LINK_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    return text.strip()


def count_words(text: str) -> int:
    """Count words in text after stripping markup."""
    cleaned = clean_text_for_words(text)
    return len(cleaned.split()) if cleaned else 0


def extract_emojis(text: str) -> list[str]:
    """Extract emoji names from text, ignoring code blocks."""
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    return _EMOJI_EXTRACT_RE.findall(text)


def count_links(text: str) -> int:
    """Count URL links in text."""
    return len(_LINK_RE.findall(text))


def top_words(texts: list[str], n: int = 10) -> list[tuple[str, int]]:
    """Return top N words (3+ letters) across multiple texts."""
    counter: Counter[str] = Counter()
    for text in texts:
        cleaned = clean_text_for_words(text)
        words = _WORD_TOKEN_RE.findall(cleaned.lower())
        counter.update(words)
    return counter.most_common(n)


def classify_message_length(word_count: int) -> str:
    """Classify a message as short/medium/long based on word count."""
    if word_count <= 5:
        return "short"
    if word_count <= 25:
        return "medium"
    return "long"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_text_processing.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/text_processing.py tests/test_analytics_text_processing.py
git commit -m "feat(v2): add text processing helpers — word count, emoji extraction, link counting"
```

---

### Task 4: Volume Analytics

**Files:**
- Create: `src/slackwrap/analytics/volume.py`
- Create: `tests/test_analytics_volume.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_volume.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def seeded_db(db):
    """DB with two users and a channel, 10 messages over 5 days."""
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="general", type="channel")
    db.commit()

    # 10 messages: 6 from U1, 4 from U2, over 5 days
    msgs = [
        (ch, u1, "1700000000.001", "hello world", 1700000000.0),       # Wed Nov 15 2023
        (ch, u1, "1700000100.001", "how are you", 1700000100.0),
        (ch, u2, "1700000200.001", "good thanks", 1700000200.0),
        (ch, u1, "1700086400.001", "morning", 1700086400.0),            # Thu Nov 16
        (ch, u2, "1700086500.001", "hey there", 1700086500.0),
        (ch, u1, "1700172800.001", "friday vibes", 1700172800.0),       # Fri Nov 17
        (ch, u2, "1700172900.001", "weekend soon", 1700172900.0),
        (ch, u1, "1700345600.001", "back to work", 1700345600.0),       # Sun Nov 19
        (ch, u2, "1700345700.001", "yep", 1700345700.0),
        (ch, u1, "1700432000.001", "new week", 1700432000.0),           # Mon Nov 20
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                          text=text, created_at=created_at)
    db.commit()
    return db, u1, u2, ch


def test_volume_total_messages(seeded_db):
    from slackwrap.analytics.volume import compute_volume

    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_messages == 10


def test_volume_per_user_split(seeded_db):
    from slackwrap.analytics.volume import compute_volume

    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.you_count == 6
    assert stats.them_count == 4
    assert stats.you_pct == 60.0
    assert stats.them_pct == 40.0


def test_volume_busiest_day(seeded_db):
    from slackwrap.analytics.volume import compute_volume

    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # Nov 15 has 3 messages — the busiest
    assert stats.busiest_day_count == 3


def test_volume_active_days(seeded_db):
    from slackwrap.analytics.volume import compute_volume

    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.active_days == 5


def test_volume_weekend_weekday_split(seeded_db):
    from slackwrap.analytics.volume import compute_volume

    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # Sun Nov 19 has 2 messages (weekend), rest are weekday
    assert stats.weekend_count == 2
    assert stats.weekday_count == 8


def test_volume_monthly_rank(seeded_db):
    from slackwrap.analytics.volume import compute_volume

    db, u1, u2, ch = seeded_db
    stats = compute_volume(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # All 10 messages in Nov 2023
    assert len(stats.monthly_rank) >= 1
    assert stats.monthly_rank[0][2] == 1  # rank 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_volume.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement volume analytics**

```python
# src/slackwrap/analytics/volume.py
from __future__ import annotations
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import VolumeStats
from slackwrap.db import Database

# System subtypes to exclude from message counts (same as v1)
SYSTEM_SUBTYPES = (
    "huddle_thread", "channel_join", "channel_leave", "channel_topic",
    "channel_purpose", "channel_name", "bot_message", "bot_add",
    "bot_remove", "file_comment", "file_mention",
    "pinned_item", "unpinned_item", "group_join", "group_leave",
    "group_topic", "group_purpose", "group_name", "channel_archive",
    "channel_unarchive", "ekm_access_denied", "reminder_add",
    "sh_room_created", "tombstone",
)


def _system_subtype_clause(alias: str = "m") -> str:
    placeholders = ", ".join("?" for _ in SYSTEM_SUBTYPES)
    return f"({alias}.subtype IS NULL OR {alias}.subtype NOT IN ({placeholders}))"


def compute_volume(db: Database, you_id: int, them_id: int, filters: Filters) -> VolumeStats:
    where, params = build_where(filters)

    # Base filter: exclude system messages, only these two users
    base = f"""
        FROM messages m
        {where}
        {"AND" if where else "WHERE"} {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    base_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    # Total and per-user counts
    row = db.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as you_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as them_count,
            MIN(m.created_at) as first_ts,
            MAX(m.created_at) as last_ts
        {base}
    """, tuple([you_id, them_id] + base_params)).fetchone()

    total = row["total"]
    if total == 0:
        return VolumeStats()

    you_count = row["you_count"]
    them_count = row["them_count"]
    first_ts = row["first_ts"]
    last_ts = row["last_ts"]
    total_days = max(int((last_ts - first_ts) / 86400) + 1, 1)
    per_week = total / max(total_days / 7, 1)

    # Busiest day
    busiest = db.execute(f"""
        SELECT date(m.created_at, 'unixepoch') as day, COUNT(*) as cnt
        {base}
        GROUP BY day ORDER BY cnt DESC LIMIT 1
    """, tuple(base_params)).fetchone()

    # Active days and weekend/weekday split
    daily = db.execute(f"""
        SELECT
            date(m.created_at, 'unixepoch') as day,
            CAST(strftime('%w', m.created_at, 'unixepoch') AS INTEGER) as dow
        {base}
        GROUP BY day
    """, tuple(base_params)).fetchall()

    active_days = len(daily)
    weekend_days = sum(1 for d in daily if d["dow"] in (0, 6))
    weekday_msgs = 0
    weekend_msgs = 0

    # Count messages by weekend/weekday
    wk_split = db.execute(f"""
        SELECT
            CASE WHEN CAST(strftime('%w', m.created_at, 'unixepoch') AS INTEGER) IN (0, 6)
                 THEN 'weekend' ELSE 'weekday' END as period,
            COUNT(*) as cnt
        {base}
        GROUP BY period
    """, tuple(base_params)).fetchall()
    for r in wk_split:
        if r["period"] == "weekend":
            weekend_msgs = r["cnt"]
        else:
            weekday_msgs = r["cnt"]

    # Monthly volumes
    monthly_rows = db.execute(f"""
        SELECT strftime('%Y-%m', m.created_at, 'unixepoch') as month, COUNT(*) as cnt
        {base}
        GROUP BY month ORDER BY month
    """, tuple(base_params)).fetchall()
    monthly_volumes = {r["month"]: r["cnt"] for r in monthly_rows}

    # Monthly rank
    sorted_months = sorted(monthly_volumes.items(), key=lambda x: x[1], reverse=True)
    monthly_rank = [(m, c, i + 1) for i, (m, c) in enumerate(sorted_months)]

    return VolumeStats(
        total_messages=total,
        you_count=you_count,
        them_count=them_count,
        you_pct=round(you_count / total * 100, 1),
        them_pct=round(them_count / total * 100, 1),
        per_week=round(per_week, 1),
        busiest_day_date=busiest["day"] if busiest else "",
        busiest_day_count=busiest["cnt"] if busiest else 0,
        active_days=active_days,
        total_days=total_days,
        weekday_count=weekday_msgs,
        weekend_count=weekend_msgs,
        messages_per_active_day=round(total / active_days, 1) if active_days else 0.0,
        monthly_volumes=monthly_volumes,
        monthly_rank=monthly_rank,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_volume.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/volume.py tests/test_analytics_volume.py
git commit -m "feat(v2): add volume analytics — message counts, busiest day, active days, weekend/weekday split"
```

---

### Task 5: Huddle Analytics

**Files:**
- Create: `src/slackwrap/analytics/huddles.py`
- Create: `tests/test_analytics_huddles.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_huddles.py
from __future__ import annotations
import json
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def seeded_huddles(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    # 5 huddles: 3 started by u1, 2 by u2
    huddles = [
        (ch, u1, 1700000000.0, 1700003600.0, 3600, json.dumps(["U1", "U2"])),   # 1h, Mon
        (ch, u2, 1700100000.0, 1700101800.0, 1800, json.dumps(["U1", "U2"])),   # 30m, Tue
        (ch, u1, 1700200000.0, 1700207200.0, 7200, json.dumps(["U1", "U2"])),   # 2h, Wed
        (ch, u1, 1700300000.0, 1700300120.0, 120, json.dumps(["U1", "U2"])),    # 2m, Thu
        (ch, u2, 1700400000.0, 1700403600.0, 3600, json.dumps(["U1", "U2"])),   # 1h, Fri
    ]
    for channel_id, created_by, start, end, dur, participants in huddles:
        db.execute(
            """INSERT INTO huddles (channel_id, created_by_user_id, started_at, ended_at,
               duration_seconds, participant_ids) VALUES (?, ?, ?, ?, ?, ?)""",
            (channel_id, created_by, start, end, dur, participants),
        )
    db.commit()
    return db, u1, u2, ch


def test_huddle_total_count(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles

    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_huddles == 5


def test_huddle_total_time(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles

    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_seconds == 3600 + 1800 + 7200 + 120 + 3600  # 16320


def test_huddle_who_starts(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles

    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.started_by_you == 3
    assert stats.started_by_them == 2


def test_huddle_longest_shortest(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles

    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.longest_seconds == 7200
    assert stats.shortest_seconds == 120


def test_huddle_median(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles

    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # Sorted durations: 120, 1800, 3600, 3600, 7200 -> median = 3600
    assert stats.median_seconds == 3600
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_huddles.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement huddle analytics**

```python
# src/slackwrap/analytics/huddles.py
from __future__ import annotations
from slackwrap.analytics.filters import Filters
from slackwrap.analytics.types import HuddleStats
from slackwrap.db import Database

DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _median(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2


def compute_huddles(db: Database, you_id: int, them_id: int, filters: Filters) -> HuddleStats:
    channel_clause = ""
    params: list = []
    if filters.channel_id is not None:
        channel_clause = "WHERE h.channel_id = ?"
        params.append(filters.channel_id)

    rows = db.execute(f"""
        SELECT h.duration_seconds, h.created_by_user_id, h.started_at,
               CAST(strftime('%w', h.started_at, 'unixepoch') AS INTEGER) as dow
        FROM huddles h
        {channel_clause}
    """, tuple(params)).fetchall()

    if not rows:
        return HuddleStats()

    durations = [r["duration_seconds"] for r in rows]
    total_seconds = sum(durations)
    total_huddles = len(rows)

    started_by_you = sum(1 for r in rows if r["created_by_user_id"] == you_id)
    started_by_them = sum(1 for r in rows if r["created_by_user_id"] == them_id)

    # Weekday breakdown
    weekday_breakdown: dict[str, int] = {}
    for r in rows:
        day_name = DAY_NAMES[r["dow"]]
        weekday_breakdown[day_name] = weekday_breakdown.get(day_name, 0) + 1

    # Span for frequency
    first_ts = min(r["started_at"] for r in rows)
    last_ts = max(r["started_at"] for r in rows)
    span_days = max(int((last_ts - first_ts) / 86400) + 1, 1)
    per_week = round(total_huddles / max(span_days / 7, 1), 1)
    per_month = round(total_huddles / max(span_days / 30, 1), 1)

    return HuddleStats(
        total_huddles=total_huddles,
        total_seconds=total_seconds,
        avg_seconds=total_seconds // total_huddles,
        median_seconds=_median(durations),
        longest_seconds=max(durations),
        shortest_seconds=min(durations),
        started_by_you=started_by_you,
        started_by_them=started_by_them,
        weekday_breakdown=weekday_breakdown,
        per_week=per_week,
        per_month=per_month,
        huddle_to_message_ratio=0.0,  # Computed by engine when combined with volume
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_huddles.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/huddles.py tests/test_analytics_huddles.py
git commit -m "feat(v2): add huddle analytics — time, count, median, who starts, weekday breakdown"
```

---

### Task 6: Response Time Analytics

**Files:**
- Create: `src/slackwrap/analytics/response_time.py`
- Create: `tests/test_analytics_response_time.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_response_time.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def conversation_db(db):
    """DB with alternating messages to test response time."""
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    # Alternating conversation: U1, U2, U1, U2 with known gaps
    msgs = [
        (ch, u1, "1700000000.001", "hey", 1700000000.0),
        (ch, u2, "1700000120.001", "hi", 1700000120.0),        # 2 min response
        (ch, u1, "1700000300.001", "question", 1700000300.0),   # 3 min response
        (ch, u2, "1700000600.001", "answer", 1700000600.0),     # 5 min response
        (ch, u1, "1700000900.001", "thanks", 1700000900.0),     # 5 min response
        # Big gap (overnight) — should be excluded
        (ch, u2, "1700050000.001", "morning", 1700050000.0),    # ~14h gap
        (ch, u1, "1700050060.001", "hey", 1700050060.0),        # 1 min response
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                          text=text, created_at=created_at)
    db.commit()
    return db, u1, u2, ch


def test_response_time_excludes_long_gaps(conversation_db):
    from slackwrap.analytics.response_time import compute_response_times

    db, u1, u2, ch = conversation_db
    stats = compute_response_times(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # The 14h gap should be excluded from response time calculations
    # Your responses: 3min (180s) to msg2, 5min (300s) to msg4, 1min (60s) to msg6
    # Their responses: 2min (120s) to msg1, 5min (300s) to msg3
    assert stats.your_avg > 0
    assert stats.their_avg > 0


def test_response_time_your_vs_their(conversation_db):
    from slackwrap.analytics.response_time import compute_response_times

    db, u1, u2, ch = conversation_db
    stats = compute_response_times(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # Both should have measurable response times
    assert stats.your_median > 0
    assert stats.their_median > 0


def test_response_time_by_hour(conversation_db):
    from slackwrap.analytics.response_time import compute_response_times

    db, u1, u2, ch = conversation_db
    stats = compute_response_times(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert isinstance(stats.by_hour, dict)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_response_time.py -v`
Expected: FAIL

- [ ] **Step 3: Implement response time analytics**

```python
# src/slackwrap/analytics/response_time.py
from __future__ import annotations
from datetime import datetime, timezone
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import ResponseTimeStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database

MAX_GAP_SECONDS = 4 * 3600  # Skip gaps > 4 hours


def _median(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2


def _build_turns(messages: list[dict]) -> list[dict]:
    """Collapse consecutive same-user messages into turns."""
    if not messages:
        return []
    turns = []
    current = {
        "user_id": messages[0]["user_id"],
        "start_ts": messages[0]["created_at"],
    }
    for msg in messages[1:]:
        if msg["user_id"] == current["user_id"]:
            pass  # Same user, extend turn
        else:
            turns.append(current)
            current = {
                "user_id": msg["user_id"],
                "start_ts": msg["created_at"],
            }
    turns.append(current)
    return turns


def compute_response_times(
    db: Database, you_id: int, them_id: int, filters: Filters
) -> ResponseTimeStats:
    where, params = build_where(filters)

    base_where = where if where else "WHERE 1=1"
    full_where = f"""
        {base_where}
        AND {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    rows = db.execute(f"""
        SELECT m.user_id, m.created_at
        FROM messages m
        {full_where}
        ORDER BY m.created_at
    """, tuple(full_params)).fetchall()

    if len(rows) < 2:
        return ResponseTimeStats()

    messages = [{"user_id": r["user_id"], "created_at": r["created_at"]} for r in rows]
    turns = _build_turns(messages)

    your_times: list[int] = []
    their_times: list[int] = []
    by_hour_raw: dict[int, list[int]] = {}

    for i in range(1, len(turns)):
        prev = turns[i - 1]
        curr = turns[i]
        delta = int(curr["start_ts"] - prev["start_ts"])

        if delta >= MAX_GAP_SECONDS:
            continue

        hour = datetime.fromtimestamp(curr["start_ts"], tz=timezone.utc).hour

        if prev["user_id"] != you_id and curr["user_id"] == you_id:
            your_times.append(delta)
        elif prev["user_id"] == you_id and curr["user_id"] != you_id:
            their_times.append(delta)

        if prev["user_id"] != curr["user_id"]:
            by_hour_raw.setdefault(hour, []).append(delta)

    by_hour = {}
    for hour, times in sorted(by_hour_raw.items()):
        if len(times) >= 3:
            by_hour[hour] = _median(times)

    fastest_hour = min(by_hour, key=by_hour.get) if by_hour else 0
    slowest_hour = max(by_hour, key=by_hour.get) if by_hour else 0

    # Monthly trend
    monthly_raw: dict[str, list[int]] = {}
    for i in range(1, len(turns)):
        prev = turns[i - 1]
        curr = turns[i]
        delta = int(curr["start_ts"] - prev["start_ts"])
        if delta >= MAX_GAP_SECONDS:
            continue
        if prev["user_id"] != curr["user_id"]:
            month = datetime.fromtimestamp(curr["start_ts"], tz=timezone.utc).strftime("%Y-%m")
            monthly_raw.setdefault(month, []).append(delta)

    monthly_trend = {m: _median(ts) for m, ts in sorted(monthly_raw.items()) if len(ts) >= 3}

    return ResponseTimeStats(
        your_median=_median(your_times),
        your_avg=int(sum(your_times) / len(your_times)) if your_times else 0,
        their_median=_median(their_times),
        their_avg=int(sum(their_times) / len(their_times)) if their_times else 0,
        fastest_hour=fastest_hour,
        fastest_hour_median=by_hour.get(fastest_hour, 0),
        slowest_hour=slowest_hour,
        slowest_hour_median=by_hour.get(slowest_hour, 0),
        by_hour=by_hour,
        monthly_trend=monthly_trend,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_response_time.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/response_time.py tests/test_analytics_response_time.py
git commit -m "feat(v2): add response time analytics — turn-based, by hour, monthly trend"
```

---

### Task 7: Streaks and Gaps

**Files:**
- Create: `src/slackwrap/analytics/streaks.py`
- Create: `tests/test_analytics_streaks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_streaks.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def streak_db(db):
    """Messages over several days with a gap."""
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    day = 86400
    base = 1700000000.0  # Wed Nov 15 2023
    # 5 consecutive days, then 3 day gap, then 2 consecutive days
    timestamps = [
        base,               # Day 1
        base + day,         # Day 2
        base + 2 * day,     # Day 3
        base + 3 * day,     # Day 4
        base + 4 * day,     # Day 5
        # Gap: Day 6, 7, 8 missing
        base + 8 * day,     # Day 9
        base + 9 * day,     # Day 10
    ]
    for i, ts in enumerate(timestamps):
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"msg {i}", created_at=ts)
    db.commit()
    return db, u1, u2, ch


def test_longest_streak(streak_db):
    from slackwrap.analytics.streaks import compute_streaks

    db, u1, u2, ch = streak_db
    stats = compute_streaks(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.longest_streak_days == 5


def test_current_streak(streak_db):
    from slackwrap.analytics.streaks import compute_streaks

    db, u1, u2, ch = streak_db
    stats = compute_streaks(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.current_streak_days == 2


def test_longest_gap(streak_db):
    from slackwrap.analytics.streaks import compute_streaks

    db, u1, u2, ch = streak_db
    stats = compute_streaks(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # 3-day gap = ~259200 seconds
    assert stats.longest_gap_seconds >= 259200


def test_milestones(streak_db):
    from slackwrap.analytics.streaks import compute_streaks

    db, u1, u2, ch = streak_db
    stats = compute_streaks(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert isinstance(stats.milestones, dict)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_streaks.py -v`
Expected: FAIL

- [ ] **Step 3: Implement streaks**

```python
# src/slackwrap/analytics/streaks.py
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import StreakStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_streaks(db: Database, you_id: int, them_id: int, filters: Filters) -> StreakStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"""
        {base_where}
        AND {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    rows = db.execute(f"""
        SELECT m.created_at FROM messages m
        {full_where}
        ORDER BY m.created_at
    """, tuple(full_params)).fetchall()

    if not rows:
        return StreakStats()

    timestamps = [r["created_at"] for r in rows]

    # Build active dates set
    active_dates = sorted({
        datetime.fromtimestamp(ts, tz=timezone.utc).date()
        for ts in timestamps
    })

    if not active_dates:
        return StreakStats()

    # Longest streak
    best_start = active_dates[0]
    best_len = 1
    streak_start = active_dates[0]
    streak_len = 1

    for i in range(1, len(active_dates)):
        if active_dates[i] == active_dates[i - 1] + timedelta(days=1):
            streak_len += 1
        else:
            if streak_len > best_len:
                best_len = streak_len
                best_start = streak_start
            streak_start = active_dates[i]
            streak_len = 1
    if streak_len > best_len:
        best_len = streak_len
        best_start = streak_start

    best_end = best_start + timedelta(days=best_len - 1)

    def _date_to_ts(d: date) -> float:
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()

    # Current streak (from last active date backwards)
    cur_len = 1
    for i in range(len(active_dates) - 2, -1, -1):
        if active_dates[i] == active_dates[i + 1] - timedelta(days=1):
            cur_len += 1
        else:
            break

    # Longest gap
    longest_gap = 0
    gap_start_ts = 0.0
    gap_end_ts = 0.0
    for i in range(1, len(timestamps)):
        gap = int(timestamps[i] - timestamps[i - 1])
        if gap > longest_gap:
            longest_gap = gap
            gap_start_ts = timestamps[i - 1]
            gap_end_ts = timestamps[i]

    # Milestones
    milestones: dict[str, str] = {}
    milestone_targets = [100, 500, 1000, 2000, 5000, 10000]
    for target in milestone_targets:
        if len(timestamps) >= target:
            ts = timestamps[target - 1]
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            milestones[f"{target}th message"] = dt.strftime("%Y-%m-%d")

    return StreakStats(
        longest_streak_days=best_len,
        longest_streak_start=_date_to_ts(best_start),
        longest_streak_end=_date_to_ts(best_end),
        current_streak_days=cur_len,
        longest_gap_seconds=longest_gap,
        longest_gap_start=gap_start_ts,
        longest_gap_end=gap_end_ts,
        milestones=milestones,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_streaks.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/streaks.py tests/test_analytics_streaks.py
git commit -m "feat(v2): add streaks analytics — longest streak, current, gaps, milestones"
```

---

### Task 8: Communication Style Analytics

**Files:**
- Create: `src/slackwrap/analytics/communication.py`
- Create: `tests/test_analytics_communication.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_communication.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def comm_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    msgs = [
        (ch, u1, "1.0", "hello world how are you doing today", 1700000000.0),
        (ch, u1, "2.0", "I think we should review the code :rocket:", 1700000100.0),
        (ch, u2, "3.0", "yeah :thumbsup:", 1700000200.0),
        (ch, u2, "4.0", "looks good :thumbsup: :rocket:", 1700000300.0),
        (ch, u1, "5.0", "great", 1700000400.0),
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        msg_id = db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                                    text=text, created_at=created_at)
    db.commit()

    # Add some reactions
    msg1_id = db.execute("SELECT id FROM messages WHERE slack_ts = '3.0'").fetchone()["id"]
    db.execute("INSERT INTO reactions (message_id, user_id, emoji_name) VALUES (?, ?, ?)",
               (msg1_id, u1, "thumbsup"))
    db.execute("INSERT INTO reactions (message_id, user_id, emoji_name) VALUES (?, ?, ?)",
               (msg1_id, u1, "heart"))
    db.commit()
    return db, u1, u2, ch


def test_avg_word_count(comm_db):
    from slackwrap.analytics.communication import compute_communication

    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_avg_words > 0
    assert stats.their_avg_words > 0


def test_emoji_extraction(comm_db):
    from slackwrap.analytics.communication import compute_communication

    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_emoji_total >= 1  # :rocket: in msg 2
    assert stats.their_emoji_total >= 2  # :thumbsup: + :rocket: in msgs 3,4


def test_reactions_given(comm_db):
    from slackwrap.analytics.communication import compute_communication

    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_reactions_given == 2  # thumbsup + heart from u1


def test_emoji_diversity(comm_db):
    from slackwrap.analytics.communication import compute_communication

    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.emoji_diversity_you >= 1
    assert stats.emoji_diversity_them >= 1


def test_message_length_distribution(comm_db):
    from slackwrap.analytics.communication import compute_communication

    db, u1, u2, ch = comm_db
    stats = compute_communication(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert "short" in stats.message_length_distribution or "medium" in stats.message_length_distribution
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_communication.py -v`
Expected: FAIL

- [ ] **Step 3: Implement communication analytics**

```python
# src/slackwrap/analytics/communication.py
from __future__ import annotations
from collections import Counter
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.text_processing import (
    clean_text_for_words, extract_emojis, count_links, top_words, classify_message_length,
)
from slackwrap.analytics.types import CommunicationStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_communication(
    db: Database, you_id: int, them_id: int, filters: Filters
) -> CommunicationStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"""
        {base_where}
        AND {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    rows = db.execute(f"""
        SELECT m.id, m.user_id, m.text, m.files_count
        FROM messages m
        {full_where}
    """, tuple(full_params)).fetchall()

    if not rows:
        return CommunicationStats()

    your_texts = []
    their_texts = []
    your_word_counts = []
    their_word_counts = []
    your_emoji_counter: Counter[str] = Counter()
    their_emoji_counter: Counter[str] = Counter()
    length_dist: Counter[str] = Counter()
    your_links = 0
    their_links = 0
    your_files = 0
    their_files = 0

    for row in rows:
        text = row["text"] or ""
        user_id = row["user_id"]
        cleaned = clean_text_for_words(text)
        wc = len(cleaned.split()) if cleaned else 0
        emojis = extract_emojis(text)
        links = count_links(text)

        if user_id == you_id:
            your_texts.append(text)
            if wc > 0:
                your_word_counts.append(wc)
            your_emoji_counter.update(emojis)
            your_links += links
            your_files += row["files_count"] or 0
        else:
            their_texts.append(text)
            if wc > 0:
                their_word_counts.append(wc)
            their_emoji_counter.update(emojis)
            their_links += links
            their_files += row["files_count"] or 0

        if wc > 0:
            length_dist[classify_message_length(wc)] += 1

    your_avg = round(sum(your_word_counts) / len(your_word_counts), 1) if your_word_counts else 0.0
    their_avg = round(sum(their_word_counts) / len(their_word_counts), 1) if their_word_counts else 0.0

    # Reactions from reactions table
    msg_ids = [row["id"] for row in rows]
    your_reactions = 0
    their_reactions = 0
    reaction_counter: Counter[str] = Counter()

    if msg_ids:
        placeholders = ", ".join("?" for _ in msg_ids)
        reaction_rows = db.execute(f"""
            SELECT r.user_id, r.emoji_name
            FROM reactions r
            WHERE r.message_id IN ({placeholders})
        """, tuple(msg_ids)).fetchall()

        for rr in reaction_rows:
            reaction_counter[rr["emoji_name"]] += 1
            if rr["user_id"] == you_id:
                your_reactions += 1
            elif rr["user_id"] == them_id:
                their_reactions += 1

    return CommunicationStats(
        your_avg_words=your_avg,
        their_avg_words=their_avg,
        your_top_words=top_words(your_texts, n=10),
        their_top_words=top_words(their_texts, n=10),
        your_emoji_total=sum(your_emoji_counter.values()),
        their_emoji_total=sum(their_emoji_counter.values()),
        your_top_emojis=your_emoji_counter.most_common(5),
        their_top_emojis=their_emoji_counter.most_common(5),
        your_reactions_given=your_reactions,
        their_reactions_given=their_reactions,
        top_reactions=reaction_counter.most_common(5),
        your_links=your_links,
        their_links=their_links,
        your_files=your_files,
        their_files=their_files,
        message_length_distribution=dict(length_dist),
        emoji_diversity_you=len(your_emoji_counter),
        emoji_diversity_them=len(their_emoji_counter),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_communication.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/communication.py tests/test_analytics_communication.py
git commit -m "feat(v2): add communication analytics — words, emoji, reactions, links, length distribution"
```

---

### Task 9: Thread Analytics

**Files:**
- Create: `src/slackwrap/analytics/threads.py`
- Create: `tests/test_analytics_threads.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_threads.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def thread_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    msgs = [
        # Top-level messages
        (ch, u1, "1.0", "start", 1700000000.0, None, 3),
        (ch, u2, "2.0", "another", 1700000100.0, None, 0),
        # Thread replies to message 1.0
        (ch, u2, "1.1", "reply 1", 1700000010.0, "1.0", 0),
        (ch, u1, "1.2", "reply 2", 1700000020.0, "1.0", 0),
        (ch, u2, "1.3", "reply 3", 1700000030.0, "1.0", 0),
        # Another top-level
        (ch, u2, "3.0", "topic", 1700000200.0, None, 2),
        (ch, u1, "3.1", "reply", 1700000210.0, "3.0", 0),
        (ch, u2, "3.2", "reply2", 1700000220.0, "3.0", 0),
    ]
    for channel_id, user_id, ts, text, created_at, thread_ts, reply_count in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                          text=text, created_at=created_at, thread_ts=thread_ts or ts,
                          reply_count=reply_count)
    db.commit()
    return db, u1, u2, ch


def test_thread_breakdown(thread_db):
    from slackwrap.analytics.threads import compute_threads

    db, u1, u2, ch = thread_db
    stats = compute_threads(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_messages == 8
    assert stats.top_level == 3  # 1.0, 2.0, 3.0
    assert stats.in_threads == 5  # 1.1, 1.2, 1.3, 3.1, 3.2


def test_who_starts_threads(thread_db):
    from slackwrap.analytics.threads import compute_threads

    db, u1, u2, ch = thread_db
    stats = compute_threads(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # u1 started thread on 1.0 (reply_count=3), u2 started thread on 3.0 (reply_count=2)
    assert stats.threads_started_by_you == 1
    assert stats.threads_started_by_them == 1


def test_thread_depth(thread_db):
    from slackwrap.analytics.threads import compute_threads

    db, u1, u2, ch = thread_db
    stats = compute_threads(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.deepest_thread == 3  # Thread 1.0 has 3 replies
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_threads.py -v`
Expected: FAIL

- [ ] **Step 3: Implement thread analytics**

```python
# src/slackwrap/analytics/threads.py
from __future__ import annotations
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import ThreadStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_threads(db: Database, you_id: int, them_id: int, filters: Filters) -> ThreadStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"""
        {base_where}
        AND {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    row = db.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN m.thread_ts IS NULL OR m.thread_ts = m.slack_ts THEN 1 ELSE 0 END) as top_level,
            SUM(CASE WHEN m.thread_ts IS NOT NULL AND m.thread_ts != m.slack_ts THEN 1 ELSE 0 END) as in_threads
        FROM messages m
        {full_where}
    """, tuple(full_params)).fetchone()

    total = row["total"]
    if total == 0:
        return ThreadStats()

    top_level = row["top_level"]
    in_threads = row["in_threads"]
    thread_pct = round(in_threads / total * 100, 1) if total else 0.0

    # Who starts threads (messages with reply_count > 0)
    thread_starters = db.execute(f"""
        SELECT m.user_id, COUNT(*) as cnt
        FROM messages m
        {full_where}
        AND m.reply_count > 0
        GROUP BY m.user_id
    """, tuple(full_params)).fetchall()

    started_by_you = 0
    started_by_them = 0
    for r in thread_starters:
        if r["user_id"] == you_id:
            started_by_you = r["cnt"]
        elif r["user_id"] == them_id:
            started_by_them = r["cnt"]

    # Thread depth: count replies per thread_ts
    thread_depths = db.execute(f"""
        SELECT m.thread_ts, COUNT(*) as depth
        FROM messages m
        {full_where}
        AND m.thread_ts IS NOT NULL AND m.thread_ts != m.slack_ts
        GROUP BY m.thread_ts
    """, tuple(full_params)).fetchall()

    deepest = max((r["depth"] for r in thread_depths), default=0)
    avg_depth = round(
        sum(r["depth"] for r in thread_depths) / len(thread_depths), 1
    ) if thread_depths else 0.0

    return ThreadStats(
        total_messages=total,
        top_level=top_level,
        in_threads=in_threads,
        thread_pct=thread_pct,
        threads_started_by_you=started_by_you,
        threads_started_by_them=started_by_them,
        deepest_thread=deepest,
        avg_thread_depth=avg_depth,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_threads.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/threads.py tests/test_analytics_threads.py
git commit -m "feat(v2): add thread analytics — breakdown, who starts, depth"
```

---

### Task 10: Trends Analytics

**Files:**
- Create: `src/slackwrap/analytics/trends.py`
- Create: `tests/test_analytics_trends.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_trends.py
from __future__ import annotations
import time
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def trend_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    now = time.time()
    day = 86400

    # 10 messages in last 30 days, 5 in previous 30 days
    for i in range(10):
        ts = now - (i * day)
        db.upsert_message(channel_id=ch, user_id=u1 if i % 2 == 0 else u2,
                          slack_ts=f"{ts}.001", text=f"recent {i}", created_at=ts)
    for i in range(5):
        ts = now - (40 + i) * day
        db.upsert_message(channel_id=ch, user_id=u1, slack_ts=f"{ts}.001",
                          text=f"older {i}", created_at=ts)
    db.commit()
    return db, u1, u2, ch


def test_30d_trend(trend_db):
    from slackwrap.analytics.trends import compute_trends

    db, u1, u2, ch = trend_db
    stats = compute_trends(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.last_30d_count == 10
    assert stats.prev_30d_count == 5
    assert stats.pct_change_30d is not None
    assert stats.pct_change_30d == 100.0  # 10 vs 5 = +100%


def test_current_month(trend_db):
    from slackwrap.analytics.trends import compute_trends

    db, u1, u2, ch = trend_db
    stats = compute_trends(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.current_month != ""
    assert stats.current_month_count > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_trends.py -v`
Expected: FAIL

- [ ] **Step 3: Implement trends**

```python
# src/slackwrap/analytics/trends.py
from __future__ import annotations
import calendar
from datetime import date, datetime, timezone
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import TrendStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_trends(db: Database, you_id: int, them_id: int, filters: Filters) -> TrendStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"""
        {base_where}
        AND {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    now = datetime.now(tz=timezone.utc)
    now_ts = now.timestamp()
    cutoff_30d = now_ts - 30 * 86400
    cutoff_60d = now_ts - 60 * 86400

    # 30-day comparison
    row = db.execute(f"""
        SELECT
            SUM(CASE WHEN m.created_at >= ? THEN 1 ELSE 0 END) as last_30d,
            SUM(CASE WHEN m.created_at >= ? AND m.created_at < ? THEN 1 ELSE 0 END) as prev_30d
        FROM messages m
        {full_where}
    """, tuple([cutoff_30d, cutoff_60d, cutoff_30d] + full_params)).fetchone()

    last_30d = row["last_30d"] or 0
    prev_30d = row["prev_30d"] or 0
    pct_30d = round((last_30d - prev_30d) / prev_30d * 100, 1) if prev_30d > 0 else None

    # Current month and YoY
    today = date.today()
    current_month = today.strftime("%Y-%m")
    yoy_month = f"{today.year - 1}-{today.strftime('%m')}"

    monthly = db.execute(f"""
        SELECT strftime('%Y-%m', m.created_at, 'unixepoch') as month, COUNT(*) as cnt
        FROM messages m
        {full_where}
        GROUP BY month
    """, tuple(full_params)).fetchall()

    monthly_map = {r["month"]: r["cnt"] for r in monthly}
    current_month_count = monthly_map.get(current_month, 0)
    yoy_count = monthly_map.get(yoy_month, None)

    # YoY with daily rate normalization
    yoy_pct = None
    days_into_month = today.day
    if yoy_count and days_into_month > 0:
        _, yoy_total_days = calendar.monthrange(today.year - 1, today.month)
        current_daily = current_month_count / days_into_month
        yoy_daily = yoy_count / yoy_total_days
        if yoy_daily > 0:
            yoy_pct = round((current_daily - yoy_daily) / yoy_daily * 100, 1)

    return TrendStats(
        last_30d_count=last_30d,
        prev_30d_count=prev_30d,
        pct_change_30d=pct_30d,
        current_month=current_month,
        current_month_count=current_month_count,
        yoy_month=yoy_month,
        yoy_count=yoy_count,
        yoy_pct_change=yoy_pct,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_trends.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/trends.py tests/test_analytics_trends.py
git commit -m "feat(v2): add trend analytics — 30-day rolling, YoY with daily rate normalization"
```

---

### Task 11: Heatmap Analytics

**Files:**
- Create: `src/slackwrap/analytics/heatmap.py`
- Create: `tests/test_analytics_heatmap.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_heatmap.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def heatmap_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    # Messages on different days/hours (UTC)
    # Mon 10am, Mon 14pm, Tue 10am, Wed 10am, Wed 10am
    msgs = [
        (ch, u1, "1.0", "msg", 1700438400.0),   # Mon Nov 20 2023 00:00 UTC
        (ch, u2, "2.0", "msg", 1700474400.0),   # Mon Nov 20 10:00 UTC
        (ch, u1, "3.0", "msg", 1700488800.0),   # Mon Nov 20 14:00 UTC
        (ch, u2, "4.0", "msg", 1700560800.0),   # Tue Nov 21 10:00 UTC
        (ch, u1, "5.0", "msg", 1700647200.0),   # Wed Nov 22 10:00 UTC
        (ch, u2, "6.0", "msg", 1700647260.0),   # Wed Nov 22 10:01 UTC
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                          text=text, created_at=created_at)
    db.commit()
    return db, u1, u2, ch


def test_heatmap_returns_data(heatmap_db):
    from slackwrap.analytics.heatmap import compute_heatmap

    db, u1, u2, ch = heatmap_db
    result = compute_heatmap(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert len(result.data) > 0
    assert len(result.x_labels) == 7  # days of week
    assert len(result.y_labels) == 24  # hours


def test_heatmap_counts_match_total(heatmap_db):
    from slackwrap.analytics.heatmap import compute_heatmap

    db, u1, u2, ch = heatmap_db
    result = compute_heatmap(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    total = sum(count for hour_data in result.data.values() for count in hour_data.values())
    assert total == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_heatmap.py -v`
Expected: FAIL

- [ ] **Step 3: Implement heatmap**

```python
# src/slackwrap/analytics/heatmap.py
from __future__ import annotations
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import HeatmapResult
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database

DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
HOUR_LABELS = [f"{h:02d}:00" for h in range(24)]


def compute_heatmap(db: Database, you_id: int, them_id: int, filters: Filters) -> HeatmapResult:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"""
        {base_where}
        AND {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    rows = db.execute(f"""
        SELECT
            CAST(strftime('%w', m.created_at, 'unixepoch') AS INTEGER) as dow,
            CAST(strftime('%H', m.created_at, 'unixepoch') AS INTEGER) as hour,
            COUNT(*) as cnt
        FROM messages m
        {full_where}
        GROUP BY dow, hour
    """, tuple(full_params)).fetchall()

    # data[dow][hour] = count
    data: dict[int, dict[int, int]] = {}
    for r in rows:
        dow = r["dow"]
        hour = r["hour"]
        if dow not in data:
            data[dow] = {}
        data[dow][hour] = r["cnt"]

    return HeatmapResult(
        data=data,
        x_labels=DAY_LABELS,
        y_labels=HOUR_LABELS,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_heatmap.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/heatmap.py tests/test_analytics_heatmap.py
git commit -m "feat(v2): add heatmap analytics — hour x day-of-week activity grid"
```

---

### Task 12: Relationship Analytics

**Files:**
- Create: `src/slackwrap/analytics/relationship.py`
- Create: `tests/test_analytics_relationship.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_relationship.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def rel_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    day = 86400
    base = 1700000000.0
    # U1 sends first message 3 out of 5 days, U2 sends first 2 out of 5 days
    msgs = [
        (ch, u1, f"{base}.001", "morning", base),
        (ch, u2, f"{base + 100}.001", "hi", base + 100),
        (ch, u1, f"{base + day}.001", "morning", base + day),
        (ch, u2, f"{base + day + 50}.001", "yo", base + day + 50),
        (ch, u2, f"{base + 2*day}.001", "hey first", base + 2*day),
        (ch, u1, f"{base + 2*day + 200}.001", "sup", base + 2*day + 200),
        (ch, u1, f"{base + 3*day}.001", "gm", base + 3*day),
        (ch, u2, f"{base + 4*day}.001", "hello", base + 4*day),
        (ch, u1, f"{base + 4*day + 60}.001", "hey", base + 4*day + 60),
    ]
    for channel_id, user_id, ts, text, created_at in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                          text=text, created_at=created_at)
    db.commit()

    # Add a pin
    msg_id = db.execute("SELECT id FROM messages LIMIT 1").fetchone()["id"]
    db.execute("INSERT INTO pins (channel_id, user_id, message_ts, pinned_at) VALUES (?, ?, ?, ?)",
               (ch, u1, f"{base}.001", base + 500))
    db.commit()
    return db, u1, u2, ch


def test_conversation_initiations(rel_db):
    from slackwrap.analytics.relationship import compute_relationship

    db, u1, u2, ch = rel_db
    stats = compute_relationship(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # U1 sends first message on days 1, 2, 4 (3 times); U2 on days 3, 5 (2 times)
    assert stats.conversation_initiations_you == 3
    assert stats.conversation_initiations_them == 2


def test_reciprocity_index(rel_db):
    from slackwrap.analytics.relationship import compute_relationship

    db, u1, u2, ch = rel_db
    stats = compute_relationship(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    # 5 msgs from u1, 4 from u2 -> ratio near 1.0 but not exactly
    assert 0.0 < stats.reciprocity_index <= 1.0


def test_first_last_message(rel_db):
    from slackwrap.analytics.relationship import compute_relationship

    db, u1, u2, ch = rel_db
    stats = compute_relationship(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.first_message is not None
    assert stats.last_message is not None
    assert stats.first_message["text"] == "morning"


def test_pinned_highlights(rel_db):
    from slackwrap.analytics.relationship import compute_relationship

    db, u1, u2, ch = rel_db
    stats = compute_relationship(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert len(stats.pinned_highlights) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_relationship.py -v`
Expected: FAIL

- [ ] **Step 3: Implement relationship analytics**

```python
# src/slackwrap/analytics/relationship.py
from __future__ import annotations
from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.types import RelationshipStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_relationship(
    db: Database, you_id: int, them_id: int, filters: Filters
) -> RelationshipStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"""
        {base_where}
        AND {_system_subtype_clause()}
        AND m.user_id IN (?, ?)
    """
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    # Conversation initiations: who sends the first message each day
    daily_first = db.execute(f"""
        SELECT date(m.created_at, 'unixepoch') as day, m.user_id, m.created_at
        FROM messages m
        {full_where}
        ORDER BY m.created_at
    """, tuple(full_params)).fetchall()

    seen_days: set[str] = set()
    initiations_you = 0
    initiations_them = 0
    for r in daily_first:
        day = r["day"]
        if day not in seen_days:
            seen_days.add(day)
            if r["user_id"] == you_id:
                initiations_you += 1
            else:
                initiations_them += 1

    # Reciprocity index: min(you, them) / max(you, them) based on message count
    counts = db.execute(f"""
        SELECT m.user_id, COUNT(*) as cnt
        FROM messages m
        {full_where}
        GROUP BY m.user_id
    """, tuple(full_params)).fetchall()

    you_count = 0
    them_count = 0
    for r in counts:
        if r["user_id"] == you_id:
            you_count = r["cnt"]
        else:
            them_count = r["cnt"]

    max_count = max(you_count, them_count)
    min_count = min(you_count, them_count)
    reciprocity = round(min_count / max_count, 2) if max_count > 0 else 0.0

    # First and last message
    first = db.execute(f"""
        SELECT m.user_id, m.text, m.created_at as ts
        FROM messages m
        {full_where}
        ORDER BY m.created_at ASC LIMIT 1
    """, tuple(full_params)).fetchone()

    last = db.execute(f"""
        SELECT m.user_id, m.text, m.created_at as ts
        FROM messages m
        {full_where}
        ORDER BY m.created_at DESC LIMIT 1
    """, tuple(full_params)).fetchone()

    def _msg_dict(row) -> dict | None:
        if not row:
            return None
        return {"user_id": row["user_id"], "text": (row["text"] or "")[:100], "ts": row["ts"]}

    # Pinned highlights
    channel_clause = ""
    pin_params: list = []
    if filters.channel_id is not None:
        channel_clause = "WHERE p.channel_id = ?"
        pin_params.append(filters.channel_id)

    pins = db.execute(f"""
        SELECT p.message_ts, p.pinned_at, p.user_id
        FROM pins p
        {channel_clause}
        ORDER BY p.pinned_at
    """, tuple(pin_params)).fetchall()

    pinned_highlights = [
        {"message_ts": p["message_ts"], "pinned_at": p["pinned_at"], "user_id": p["user_id"]}
        for p in pins
    ]

    # Shared channel distribution
    channel_dist: dict[str, int] = {}
    if not filters.channel_id:
        ch_rows = db.execute(f"""
            SELECT c.name, COUNT(*) as cnt
            FROM messages m
            JOIN channels c ON c.id = m.channel_id
            {full_where}
            GROUP BY c.name
            ORDER BY cnt DESC
        """, tuple(full_params)).fetchall()
        channel_dist = {r["name"]: r["cnt"] for r in ch_rows}

    return RelationshipStats(
        reciprocity_index=reciprocity,
        conversation_initiations_you=initiations_you,
        conversation_initiations_them=initiations_them,
        first_message=_msg_dict(first),
        last_message=_msg_dict(last),
        pinned_highlights=pinned_highlights,
        shared_channel_distribution=channel_dist,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_relationship.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/relationship.py tests/test_analytics_relationship.py
git commit -m "feat(v2): add relationship analytics — reciprocity, initiations, first/last, pins"
```

---

### Task 13: Rollup Computation

**Files:**
- Create: `src/slackwrap/analytics/rollups.py`
- Create: `tests/test_analytics_rollups.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_rollups.py
from __future__ import annotations
import pytest


@pytest.fixture
def rollup_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    day = 86400
    base = 1700000000.0  # Nov 15 2023
    for i in range(20):
        ts = base + i * day
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"msg {i} hello world", created_at=ts)
    db.commit()
    return db, u1, u2


def test_compute_weekly_rollups(rollup_db):
    from slackwrap.analytics.rollups import compute_rollups

    db, u1, u2 = rollup_db
    compute_rollups(db, you_id=u1, them_id=u2, relationship_key=f"{u1}:{u2}")

    rows = db.execute("SELECT * FROM weekly_stats WHERE relationship_key = ?",
                       (f"{u1}:{u2}",)).fetchall()
    assert len(rows) >= 1
    total = sum(r["message_count"] for r in rows)
    assert total == 20


def test_compute_monthly_rollups(rollup_db):
    from slackwrap.analytics.rollups import compute_rollups

    db, u1, u2 = rollup_db
    compute_rollups(db, you_id=u1, them_id=u2, relationship_key=f"{u1}:{u2}")

    rows = db.execute("SELECT * FROM monthly_stats WHERE relationship_key = ?",
                       (f"{u1}:{u2}",)).fetchall()
    assert len(rows) >= 1
    total = sum(r["message_count"] for r in rows)
    assert total == 20


def test_rollups_are_idempotent(rollup_db):
    from slackwrap.analytics.rollups import compute_rollups

    db, u1, u2 = rollup_db
    key = f"{u1}:{u2}"
    compute_rollups(db, you_id=u1, them_id=u2, relationship_key=key)
    compute_rollups(db, you_id=u1, them_id=u2, relationship_key=key)

    rows = db.execute("SELECT * FROM weekly_stats WHERE relationship_key = ?", (key,)).fetchall()
    total = sum(r["message_count"] for r in rows)
    assert total == 20  # Not doubled
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_rollups.py -v`
Expected: FAIL

- [ ] **Step 3: Implement rollups**

```python
# src/slackwrap/analytics/rollups.py
from __future__ import annotations
from slackwrap.analytics.volume import SYSTEM_SUBTYPES
from slackwrap.db import Database


def compute_rollups(db: Database, you_id: int, them_id: int, relationship_key: str) -> None:
    """Compute and store weekly and monthly rollup stats for a relationship."""
    subtype_placeholders = ", ".join("?" for _ in SYSTEM_SUBTYPES)
    subtype_clause = f"(m.subtype IS NULL OR m.subtype NOT IN ({subtype_placeholders}))"
    base_params = list(SYSTEM_SUBTYPES) + [you_id, them_id]

    # Weekly rollups
    weekly_rows = db.execute(f"""
        SELECT
            date(m.created_at, 'unixepoch', 'weekday 0', '-6 days') as week_start,
            COUNT(*) as message_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as your_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as their_count
        FROM messages m
        WHERE {subtype_clause}
        AND m.user_id IN (?, ?)
        GROUP BY week_start
        ORDER BY week_start
    """, tuple([you_id, them_id] + base_params)).fetchall()

    for row in weekly_rows:
        db.execute("""
            INSERT INTO weekly_stats (relationship_key, week_start, message_count,
                your_count, their_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(relationship_key, week_start) DO UPDATE SET
                message_count=excluded.message_count,
                your_count=excluded.your_count,
                their_count=excluded.their_count
        """, (relationship_key, row["week_start"], row["message_count"],
              row["your_count"], row["their_count"]))

    # Monthly rollups
    monthly_rows = db.execute(f"""
        SELECT
            strftime('%Y-%m', m.created_at, 'unixepoch') as month,
            COUNT(*) as message_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as your_count,
            SUM(CASE WHEN m.user_id = ? THEN 1 ELSE 0 END) as their_count
        FROM messages m
        WHERE {subtype_clause}
        AND m.user_id IN (?, ?)
        GROUP BY month
        ORDER BY month
    """, tuple([you_id, them_id] + base_params)).fetchall()

    for row in monthly_rows:
        db.execute("""
            INSERT INTO monthly_stats (relationship_key, month, message_count,
                your_count, their_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(relationship_key, month) DO UPDATE SET
                message_count=excluded.message_count,
                your_count=excluded.your_count,
                their_count=excluded.their_count
        """, (relationship_key, row["month"], row["message_count"],
              row["your_count"], row["their_count"]))

    db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_rollups.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/analytics/rollups.py tests/test_analytics_rollups.py
git commit -m "feat(v2): add rollup computation — weekly and monthly stats with idempotent upserts"
```

---

### Task 14: Analytics Engine Coordinator

Ties everything together — the `AnalyticsEngine` class that delegates to individual modules.

**Files:**
- Create: `src/slackwrap/analytics/engine.py`
- Modify: `src/slackwrap/analytics/__init__.py`
- Create: `tests/test_analytics_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics_engine.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def engine_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    msgs = [
        (ch, u1, "1.0", "hello world", 1700000000.0, None, 0),
        (ch, u2, "2.0", "hey there :rocket:", 1700000100.0, None, 0),
        (ch, u1, "3.0", "let's discuss", 1700000200.0, None, 2),
        (ch, u2, "3.1", "sure", 1700000210.0, "3.0", 0),
        (ch, u1, "3.2", "ok great", 1700000220.0, "3.0", 0),
    ]
    for channel_id, user_id, ts, text, created_at, thread_ts, reply_count in msgs:
        db.upsert_message(channel_id=channel_id, user_id=user_id, slack_ts=ts,
                          text=text, created_at=created_at,
                          thread_ts=thread_ts or ts, reply_count=reply_count)
    db.commit()
    return db, u1, u2, ch


def test_engine_volume(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine

    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    stats = engine.volume(you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_messages == 5


def test_engine_threads(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine

    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    stats = engine.threads(you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_messages == 5
    assert stats.in_threads >= 2


def test_engine_communication(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine

    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    stats = engine.communication(you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.your_avg_words > 0


def test_engine_heatmap(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine

    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    result = engine.heatmap(you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert len(result.x_labels) == 7


def test_engine_text_search(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine

    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    results = engine.text_search("hello")
    assert len(results) >= 1


def test_engine_raw_sql(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine

    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    result = engine.raw_sql("SELECT COUNT(*) as cnt FROM messages")
    assert result.rows[0]["cnt"] == 5


def test_engine_rollups(engine_db):
    from slackwrap.analytics.engine import AnalyticsEngine

    db, u1, u2, ch = engine_db
    engine = AnalyticsEngine(db)
    engine.compute_rollups(you_id=u1, them_id=u2, relationship_key=f"{u1}:{u2}")

    rows = db.execute("SELECT * FROM weekly_stats").fetchall()
    assert len(rows) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_analytics_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the engine**

```python
# src/slackwrap/analytics/engine.py
from __future__ import annotations
from slackwrap.analytics.filters import Filters
from slackwrap.analytics.types import (
    VolumeStats, HuddleStats, ResponseTimeStats, ThreadStats,
    CommunicationStats, StreakStats, TrendStats, HeatmapResult,
    RelationshipStats, QueryResult,
)
from slackwrap.analytics.volume import compute_volume
from slackwrap.analytics.huddles import compute_huddles
from slackwrap.analytics.response_time import compute_response_times
from slackwrap.analytics.threads import compute_threads
from slackwrap.analytics.communication import compute_communication
from slackwrap.analytics.streaks import compute_streaks
from slackwrap.analytics.trends import compute_trends
from slackwrap.analytics.heatmap import compute_heatmap
from slackwrap.analytics.relationship import compute_relationship
from slackwrap.analytics.rollups import compute_rollups as _compute_rollups
from slackwrap.db import Database


class AnalyticsEngine:
    def __init__(self, db: Database):
        self.db = db

    def volume(self, you_id: int, them_id: int, filters: Filters) -> VolumeStats:
        return compute_volume(self.db, you_id, them_id, filters)

    def huddles(self, you_id: int, them_id: int, filters: Filters) -> HuddleStats:
        return compute_huddles(self.db, you_id, them_id, filters)

    def response_times(self, you_id: int, them_id: int, filters: Filters) -> ResponseTimeStats:
        return compute_response_times(self.db, you_id, them_id, filters)

    def threads(self, you_id: int, them_id: int, filters: Filters) -> ThreadStats:
        return compute_threads(self.db, you_id, them_id, filters)

    def communication(self, you_id: int, them_id: int, filters: Filters) -> CommunicationStats:
        return compute_communication(self.db, you_id, them_id, filters)

    def streaks(self, you_id: int, them_id: int, filters: Filters) -> StreakStats:
        return compute_streaks(self.db, you_id, them_id, filters)

    def trends(self, you_id: int, them_id: int, filters: Filters) -> TrendStats:
        return compute_trends(self.db, you_id, them_id, filters)

    def heatmap(self, you_id: int, them_id: int, filters: Filters) -> HeatmapResult:
        return compute_heatmap(self.db, you_id, them_id, filters)

    def relationship(self, you_id: int, them_id: int, filters: Filters) -> RelationshipStats:
        return compute_relationship(self.db, you_id, them_id, filters)

    def compute_rollups(self, you_id: int, them_id: int, relationship_key: str) -> None:
        _compute_rollups(self.db, you_id, them_id, relationship_key)

    def text_search(self, query: str, limit: int = 50) -> list[dict]:
        rows = self.db.execute("""
            SELECT m.id, m.user_id, m.text, m.created_at, m.channel_id, m.slack_ts
            FROM messages m
            JOIN messages_fts ON messages_fts.rowid = m.id
            WHERE messages_fts MATCH ?
            ORDER BY m.created_at DESC
            LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]

    def raw_sql(self, query: str, params: tuple = ()) -> QueryResult:
        cursor = self.db.execute(query, params)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return QueryResult(
            rows=[dict(r) for r in rows],
            columns=columns,
            row_count=len(rows),
        )
```

- [ ] **Step 4: Update the package init**

```python
# src/slackwrap/analytics/__init__.py
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters
from slackwrap.analytics.types import (
    VolumeStats, HuddleStats, ResponseTimeStats, ThreadStats,
    CommunicationStats, StreakStats, TrendStats, HeatmapResult,
    RelationshipStats, QueryResult,
)

__all__ = [
    "AnalyticsEngine", "Filters",
    "VolumeStats", "HuddleStats", "ResponseTimeStats", "ThreadStats",
    "CommunicationStats", "StreakStats", "TrendStats", "HeatmapResult",
    "RelationshipStats", "QueryResult",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_analytics_engine.py -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `python3 -m pytest tests/test_analytics_*.py -v`
Expected: All analytics tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/slackwrap/analytics/engine.py src/slackwrap/analytics/__init__.py tests/test_analytics_engine.py
git commit -m "feat(v2): add AnalyticsEngine coordinator — delegates to all analytics modules, FTS search, raw SQL"
```

---

## Plan Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Filters + SQL WHERE builder | 9 |
| 2 | Result types (10 dataclasses) | 10 |
| 3 | Text processing helpers | 12 |
| 4 | Volume analytics | 6 |
| 5 | Huddle analytics | 5 |
| 6 | Response time analytics | 3 |
| 7 | Streaks and gaps | 4 |
| 8 | Communication style | 5 |
| 9 | Thread analytics | 3 |
| 10 | Trends (30d, YoY) | 2 |
| 11 | Heatmap (hour x day) | 2 |
| 12 | Relationship (reciprocity, initiations) | 4 |
| 13 | Rollup computation | 3 |
| 14 | AnalyticsEngine coordinator | 7 |

**Total: 14 tasks, 75 tests, ~14 commits**

After this plan, the analytics engine is complete: every view (Wrapped story, explorer, deep dives, chat) can query any metric through the AnalyticsEngine. Plan 3 (TUI) and Plan 4 (Web View) will consume this engine directly.
