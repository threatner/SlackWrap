# SlackWrap v2 — Plan 5: AI Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local LLM integration via Ollama for batch AI insights (tone analysis, narratives, fun facts), message embeddings via sqlite-vec for semantic search, and a conversational chat layer with query routing — wiring up the TUI and web chat stubs.

**Architecture:** An `OllamaClient` wraps the ollama Python SDK with connection detection and graceful degradation. A `BatchInsights` module generates structured AI insights at sync time, cached in the `ai_insights` table. An `Embeddings` module computes message window embeddings stored via sqlite-vec. A `ChatEngine` with query routing classifies questions and routes them to stat lookups, SQL generation, semantic search, or cached insights. The TUI ChatScreen and web chat route are wired to the ChatEngine.

**Tech Stack:** ollama (Python SDK), sqlite-vec, Python 3.10+

**Spec:** `docs/superpowers/specs/2026-04-09-slackwrap-v2-design.md` (AI Layer section)

**Depends on:** Plans 1-4 (Data Layer, Analytics Engine, TUI, Web View)

---

## File Structure

```
src/slackwrap/
  ai/
    __init__.py
    ollama_client.py    # OllamaClient — connection check, chat, embed, structured output
    insights.py         # BatchInsights — generate and cache AI insights per relationship
    embeddings.py       # Embeddings — compute and store message window embeddings
    chat_engine.py      # ChatEngine — query routing, context building, session management
    prompts.py          # System prompts and prompt templates for all AI operations
    sampler.py          # Message sampling — stratified sampling for LLM context
  tui/screens/
    chat.py             # MODIFY: wire to ChatEngine
  web/routes/
    chat.py             # MODIFY: add POST endpoint for chat, wire to ChatEngine
  web/templates/
    chat.html           # MODIFY: add interactive chat UI with JS
tests/
  test_ai_ollama.py
  test_ai_insights.py
  test_ai_embeddings.py
  test_ai_chat_engine.py
  test_ai_sampler.py
```

---

### Task 1: Ollama Client Wrapper

**Files:**
- Create: `src/slackwrap/ai/__init__.py`
- Create: `src/slackwrap/ai/ollama_client.py`
- Create: `tests/test_ai_ollama.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai_ollama.py
from __future__ import annotations
from unittest.mock import patch, MagicMock


def test_is_available_returns_false_when_not_running():
    from slackwrap.ai.ollama_client import OllamaClient

    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        instance = MockClient.return_value
        instance.list.side_effect = Exception("Connection refused")
        client = OllamaClient()
        assert client.is_available() is False


def test_is_available_returns_true_when_running():
    from slackwrap.ai.ollama_client import OllamaClient

    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        instance = MockClient.return_value
        instance.list.return_value = {"models": []}
        client = OllamaClient()
        assert client.is_available() is True


def test_chat_returns_response_text():
    from slackwrap.ai.ollama_client import OllamaClient

    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        instance = MockClient.return_value
        mock_resp = MagicMock()
        mock_resp.message.content = "Hello! I can help with that."
        instance.chat.return_value = mock_resp
        client = OllamaClient()
        result = client.chat(messages=[{"role": "user", "content": "hi"}])
        assert result == "Hello! I can help with that."


def test_chat_with_json_format():
    from slackwrap.ai.ollama_client import OllamaClient

    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        instance = MockClient.return_value
        mock_resp = MagicMock()
        mock_resp.message.content = '{"tone": "friendly", "confidence": 0.9}'
        instance.chat.return_value = mock_resp
        client = OllamaClient()
        result = client.chat_json(
            messages=[{"role": "user", "content": "analyze tone"}],
            schema={"type": "object", "properties": {"tone": {"type": "string"}}},
        )
        assert result["tone"] == "friendly"


def test_embed_returns_vectors():
    from slackwrap.ai.ollama_client import OllamaClient

    with patch("slackwrap.ai.ollama_client.Client") as MockClient:
        instance = MockClient.return_value
        instance.embed.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        client = OllamaClient()
        vectors = client.embed(["hello world"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 3


def test_default_models():
    from slackwrap.ai.ollama_client import OllamaClient

    client = OllamaClient()
    assert client.chat_model == "llama3.1:8b"
    assert client.embed_model == "nomic-embed-text"


def test_custom_models():
    from slackwrap.ai.ollama_client import OllamaClient

    client = OllamaClient(chat_model="mistral", embed_model="mxbai-embed-large")
    assert client.chat_model == "mistral"
    assert client.embed_model == "mxbai-embed-large"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_ollama.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement OllamaClient**

```python
# src/slackwrap/ai/__init__.py
```

```python
# src/slackwrap/ai/ollama_client.py
from __future__ import annotations
import json
from ollama import Client


class OllamaClient:
    def __init__(self, host: str = "http://localhost:11434",
                 chat_model: str = "llama3.1:8b",
                 embed_model: str = "nomic-embed-text"):
        self.host = host
        self.chat_model = chat_model
        self.embed_model = embed_model
        self._client = Client(host=host)

    def is_available(self) -> bool:
        try:
            self._client.list()
            return True
        except Exception:
            return False

    def chat(self, messages: list[dict], model: str | None = None,
             temperature: float = 0.7) -> str:
        response = self._client.chat(
            model=model or self.chat_model,
            messages=messages,
            options={"temperature": temperature},
        )
        return response.message.content

    def chat_json(self, messages: list[dict], schema: dict,
                  model: str | None = None, temperature: float = 0.0) -> dict:
        response = self._client.chat(
            model=model or self.chat_model,
            messages=messages,
            format=schema,
            options={"temperature": temperature},
        )
        return json.loads(response.message.content)

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        response = self._client.embed(
            model=model or self.embed_model,
            input=texts,
        )
        return response["embeddings"]

    def embed_single(self, text: str, model: str | None = None) -> list[float]:
        vectors = self.embed([text], model=model)
        return vectors[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_ollama.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/ai/ tests/test_ai_ollama.py
git commit -m "feat(v2): add OllamaClient — connection check, chat, structured JSON, embeddings"
```

---

### Task 2: Message Sampler

**Files:**
- Create: `src/slackwrap/ai/sampler.py`
- Create: `tests/test_ai_sampler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai_sampler.py
from __future__ import annotations
import pytest
from slackwrap.analytics.filters import Filters


@pytest.fixture
def sampler_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    # 60 messages over 2 months
    for i in range(60):
        ts = 1700049600.0 + i * 86400
        user = u1 if i % 2 == 0 else u2
        hour = (i * 3) % 24
        created = ts + hour * 3600
        text = f"message {i} with some content about {'work' if i % 3 == 0 else 'fun'}"
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{created}.001",
                          text=text, created_at=created)
    db.commit()
    return db, u1, u2, ch


def test_sample_messages_returns_limited_set(sampler_db):
    from slackwrap.ai.sampler import sample_messages

    db, u1, u2, ch = sampler_db
    samples = sample_messages(db, user_id=u1, channel_id=ch, per_month=5)
    assert len(samples) <= 20  # ~5 per month, 2 months max


def test_sample_messages_includes_text(sampler_db):
    from slackwrap.ai.sampler import sample_messages

    db, u1, u2, ch = sampler_db
    samples = sample_messages(db, user_id=u1, channel_id=ch, per_month=5)
    assert all("text" in s for s in samples)
    assert all("created_at" in s for s in samples)


def test_sample_messages_for_specific_user(sampler_db):
    from slackwrap.ai.sampler import sample_messages

    db, u1, u2, ch = sampler_db
    samples = sample_messages(db, user_id=u1, channel_id=ch, per_month=5)
    assert all(s["user_id"] == u1 for s in samples)


def test_sample_conversation_windows(sampler_db):
    from slackwrap.ai.sampler import sample_conversation_windows

    db, u1, u2, ch = sampler_db
    windows = sample_conversation_windows(db, channel_id=ch, window_size=10, stride=5)
    assert len(windows) > 0
    assert all(len(w["messages"]) <= 10 for w in windows)


def test_build_stats_summary(sampler_db):
    from slackwrap.ai.sampler import build_stats_summary
    from slackwrap.analytics.engine import AnalyticsEngine
    from slackwrap.analytics.filters import Filters

    db, u1, u2, ch = sampler_db
    engine = AnalyticsEngine(db)
    summary = build_stats_summary(engine, you_id=u1, them_id=u2)
    assert "total_messages" in summary
    assert "your_name" not in summary  # raw stats, no names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_sampler.py -v`
Expected: FAIL

- [ ] **Step 3: Implement sampler**

```python
# src/slackwrap/ai/sampler.py
from __future__ import annotations
from dataclasses import asdict
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def sample_messages(db: Database, user_id: int, channel_id: int,
                    per_month: int = 20) -> list[dict]:
    """Sample ~per_month messages per calendar month for a specific user.

    Stratified by time of day to get variety. Returns dicts with
    text, created_at, user_id, slack_ts.
    """
    subtype_clause = _system_subtype_clause()
    params = list(SYSTEM_SUBTYPES) + [user_id, channel_id]

    rows = db.execute(f"""
        SELECT m.user_id, m.text, m.created_at, m.slack_ts,
               strftime('%Y-%m', m.created_at, 'unixepoch') as month,
               CAST(strftime('%H', m.created_at, 'unixepoch') AS INTEGER) as hour
        FROM messages m
        WHERE {subtype_clause}
        AND m.user_id = ?
        AND m.channel_id = ?
        AND m.text IS NOT NULL AND m.text != ''
        ORDER BY m.created_at
    """, tuple(params)).fetchall()

    # Group by month, then pick evenly spaced samples
    by_month: dict[str, list[dict]] = {}
    for r in rows:
        month = r["month"]
        if month not in by_month:
            by_month[month] = []
        by_month[month].append({
            "user_id": r["user_id"],
            "text": r["text"],
            "created_at": r["created_at"],
            "slack_ts": r["slack_ts"],
            "hour": r["hour"],
        })

    samples = []
    for month, msgs in sorted(by_month.items()):
        if len(msgs) <= per_month:
            samples.extend(msgs)
        else:
            step = len(msgs) / per_month
            for i in range(per_month):
                idx = int(i * step)
                samples.append(msgs[idx])

    return samples


def sample_conversation_windows(db: Database, channel_id: int,
                                 window_size: int = 10,
                                 stride: int = 5) -> list[dict]:
    """Create sliding windows of messages for embedding.

    Each window is a dict with 'messages' (list of text) and
    'start_ts'/'end_ts' timestamps.
    """
    subtype_clause = _system_subtype_clause()
    params = list(SYSTEM_SUBTYPES) + [channel_id]

    rows = db.execute(f"""
        SELECT m.id, m.text, m.created_at
        FROM messages m
        WHERE {subtype_clause}
        AND m.channel_id = ?
        AND m.text IS NOT NULL AND m.text != ''
        ORDER BY m.created_at
    """, tuple(params)).fetchall()

    messages = [{"id": r["id"], "text": r["text"], "created_at": r["created_at"]} for r in rows]
    windows = []

    for start in range(0, max(len(messages) - window_size + 1, 1), stride):
        chunk = messages[start:start + window_size]
        if not chunk:
            continue
        windows.append({
            "messages": [m["text"] for m in chunk],
            "message_ids": [m["id"] for m in chunk],
            "start_ts": chunk[0]["created_at"],
            "end_ts": chunk[-1]["created_at"],
        })

    return windows


def build_stats_summary(engine: AnalyticsEngine, you_id: int, them_id: int) -> dict:
    """Build a compact stats summary dict for LLM context."""
    filters = Filters()
    vol = engine.volume(you_id=you_id, them_id=them_id, filters=filters)
    streaks = engine.streaks(you_id=you_id, them_id=them_id, filters=filters)
    resp = engine.response_times(you_id=you_id, them_id=them_id, filters=filters)
    comm = engine.communication(you_id=you_id, them_id=them_id, filters=filters)
    trends = engine.trends(you_id=you_id, them_id=them_id, filters=filters)

    return {
        "total_messages": vol.total_messages,
        "you_count": vol.you_count,
        "them_count": vol.them_count,
        "total_days": vol.total_days,
        "active_days": vol.active_days,
        "per_week": vol.per_week,
        "busiest_day": vol.busiest_day_date,
        "busiest_day_count": vol.busiest_day_count,
        "longest_streak": streaks.longest_streak_days,
        "current_streak": streaks.current_streak_days,
        "your_median_response": resp.your_median,
        "their_median_response": resp.their_median,
        "your_avg_words": comm.your_avg_words,
        "their_avg_words": comm.their_avg_words,
        "your_emoji_total": comm.your_emoji_total,
        "their_emoji_total": comm.their_emoji_total,
        "last_30d": trends.last_30d_count,
        "prev_30d": trends.prev_30d_count,
        "milestones": streaks.milestones,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_sampler.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/ai/sampler.py tests/test_ai_sampler.py
git commit -m "feat(v2): add message sampler — stratified sampling, conversation windows, stats summary"
```

---

### Task 3: Prompt Templates

**Files:**
- Create: `src/slackwrap/ai/prompts.py`
- Create: `tests/test_ai_prompts.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai_prompts.py
from __future__ import annotations


def test_tone_prompt_includes_messages():
    from slackwrap.ai.prompts import build_tone_prompt

    messages = [
        {"text": "hey how are you", "created_at": 1700000000.0},
        {"text": "great work on the PR!", "created_at": 1700001000.0},
    ]
    prompt = build_tone_prompt(messages, month="2023-11")
    assert "2023-11" in prompt
    assert "hey how are you" in prompt


def test_fun_facts_prompt_includes_stats():
    from slackwrap.ai.prompts import build_fun_facts_prompt

    stats = {"total_messages": 5000, "active_days": 240, "longest_streak": 47}
    prompt = build_fun_facts_prompt(stats)
    assert "5000" in prompt or "5,000" in prompt
    assert "47" in prompt


def test_chat_system_prompt_includes_schema():
    from slackwrap.ai.prompts import build_chat_system_prompt

    stats = {"total_messages": 1000}
    prompt = build_chat_system_prompt(stats_summary=stats, your_name="Alice", their_name="Bob")
    assert "Alice" in prompt
    assert "Bob" in prompt
    assert "messages" in prompt.lower()


def test_style_prompt_includes_stats():
    from slackwrap.ai.prompts import build_style_prompt

    stats = {"your_avg_words": 11.2, "their_avg_words": 8.7, "your_emoji_total": 50}
    prompt = build_style_prompt(stats, your_name="Alice", their_name="Bob")
    assert "Alice" in prompt
    assert "11.2" in prompt


def test_sql_generation_prompt():
    from slackwrap.ai.prompts import build_sql_prompt

    prompt = build_sql_prompt(question="How many messages in January?",
                              schema_description="messages(id, text, created_at, user_id)")
    assert "January" in prompt
    assert "messages" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_prompts.py -v`
Expected: FAIL

- [ ] **Step 3: Implement prompts**

```python
# src/slackwrap/ai/prompts.py
from __future__ import annotations
import json
from datetime import datetime, timezone


def build_tone_prompt(messages: list[dict], month: str) -> str:
    msg_texts = []
    for m in messages[:20]:
        ts = m.get("created_at", 0)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        msg_texts.append(f"[{dt.strftime('%Y-%m-%d %H:%M')}] {m['text']}")

    return f"""Analyze the tone and communication style of these messages from {month}.

Messages:
{chr(10).join(msg_texts)}

Respond with JSON:
{{
    "tone_label": "one of: formal, casual, friendly, professional, terse, enthusiastic",
    "confidence": 0.0 to 1.0,
    "narrative": "A 1-2 sentence description of the communication tone this month"
}}"""


def build_style_prompt(stats: dict, your_name: str, their_name: str) -> str:
    return f"""Based on these communication statistics, describe the communication style of each person.

{your_name}:
- Average words per message: {stats.get('your_avg_words', 0)}
- Emoji used: {stats.get('your_emoji_total', 0)}
- Reactions given: {stats.get('your_reactions_given', 0)}

{their_name}:
- Average words per message: {stats.get('their_avg_words', 0)}
- Emoji used: {stats.get('their_emoji_total', 0)}
- Reactions given: {stats.get('their_reactions_given', 0)}

Respond with JSON:
{{
    "your_style": "1-2 sentence description of {your_name}'s style",
    "their_style": "1-2 sentence description of {their_name}'s style",
    "comparison": "1 sentence comparing the two styles"
}}"""


def build_fun_facts_prompt(stats: dict) -> str:
    stats_text = json.dumps(stats, indent=2, default=str)
    return f"""Based on these Slack conversation statistics, generate 5 fun, surprising, or interesting observations. Be specific with numbers. Include projections where interesting.

Stats:
{stats_text}

Respond with JSON:
{{
    "facts": [
        "fun fact 1",
        "fun fact 2",
        "fun fact 3",
        "fun fact 4",
        "fun fact 5"
    ]
}}"""


def build_trajectory_prompt(monthly_volumes: dict, streaks: dict, response_trends: dict) -> str:
    return f"""Describe the trajectory of this Slack relationship over time based on the data.

Monthly message volumes: {json.dumps(monthly_volumes, default=str)}
Streak data: {json.dumps(streaks, default=str)}
Response time trends: {json.dumps(response_trends, default=str)}

Respond with JSON:
{{
    "narrative": "A 2-3 sentence narrative arc of this relationship",
    "phase": "one of: growing, stable, declining, fluctuating",
    "peak_period": "the month or period with highest engagement"
}}"""


def build_chat_system_prompt(stats_summary: dict, your_name: str, their_name: str) -> str:
    stats_text = json.dumps(stats_summary, indent=2, default=str)
    return f"""You are SlackWrap AI, an assistant that answers questions about {your_name}'s Slack conversation history with {their_name}.

You have access to these pre-computed statistics:
{stats_text}

The conversation data is stored in a SQLite database with these tables:
- messages(id, channel_id, user_id, slack_ts, text, subtype, thread_ts, reply_count, files_count, created_at)
- reactions(id, message_id, user_id, emoji_name)
- huddles(id, channel_id, created_by_user_id, started_at, ended_at, duration_seconds, participant_ids)
- weekly_stats(relationship_key, week_start, message_count, your_count, their_count)
- monthly_stats(relationship_key, month, message_count, your_count, their_count)

When asked about specific data, you can generate SQL queries. Wrap SQL in ```sql blocks.
When asked about tone or patterns, use the pre-computed statistics above.
Be concise and specific. Use actual numbers from the stats."""


def build_sql_prompt(question: str, schema_description: str) -> str:
    return f"""Generate a SQLite SQL query to answer this question about Slack messages:

Question: {question}

Database schema:
{schema_description}

Return ONLY the SQL query, no explanation. The query must be read-only (SELECT only).
Do not use DELETE, UPDATE, INSERT, DROP, or ALTER."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_prompts.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/ai/prompts.py tests/test_ai_prompts.py
git commit -m "feat(v2): add prompt templates — tone, style, fun facts, trajectory, chat, SQL generation"
```

---

### Task 4: Batch Insights

**Files:**
- Create: `src/slackwrap/ai/insights.py`
- Create: `tests/test_ai_insights.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai_insights.py
from __future__ import annotations
import json
import hashlib
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def insights_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(30):
        ts = 1700049600.0 + i * 86400
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"msg {i} about work and stuff", created_at=ts)
    db.commit()
    return db, u1, u2, ch


def test_generate_insights_stores_in_db(insights_db):
    from slackwrap.ai.insights import generate_insights

    db, u1, u2, ch = insights_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.chat_json.return_value = {
        "facts": ["fact 1", "fact 2", "fact 3", "fact 4", "fact 5"]
    }

    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=f"{u1}:{u2}", your_name="Alice", their_name="Bob")

    rows = db.execute("SELECT * FROM ai_insights WHERE relationship_key = ?",
                       (f"{u1}:{u2}",)).fetchall()
    assert len(rows) >= 1


def test_generate_insights_skips_when_cached(insights_db):
    from slackwrap.ai.insights import generate_insights

    db, u1, u2, ch = insights_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.chat_json.return_value = {"facts": ["a", "b", "c", "d", "e"]}

    key = f"{u1}:{u2}"
    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=key, your_name="Alice", their_name="Bob")
    call_count_1 = mock_ollama.chat_json.call_count

    # Second call should skip (cached)
    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=key, your_name="Alice", their_name="Bob")
    call_count_2 = mock_ollama.chat_json.call_count

    assert call_count_2 == call_count_1  # No new calls


def test_generate_insights_skips_when_unavailable(insights_db):
    from slackwrap.ai.insights import generate_insights

    db, u1, u2, ch = insights_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = False

    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=f"{u1}:{u2}", your_name="Alice", their_name="Bob")

    rows = db.execute("SELECT * FROM ai_insights").fetchall()
    assert len(rows) == 0


def test_get_cached_insights(insights_db):
    from slackwrap.ai.insights import generate_insights, get_cached_insights

    db, u1, u2, ch = insights_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.chat_json.return_value = {"facts": ["fact 1", "fact 2", "fact 3", "fact 4", "fact 5"]}

    key = f"{u1}:{u2}"
    generate_insights(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                      relationship_key=key, your_name="Alice", their_name="Bob")

    cached = get_cached_insights(db, relationship_key=key)
    assert len(cached) >= 1
    assert any(c["insight_type"] == "fun_facts" for c in cached)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_insights.py -v`
Expected: FAIL

- [ ] **Step 3: Implement batch insights**

```python
# src/slackwrap/ai/insights.py
from __future__ import annotations
import hashlib
import json
import time
from dataclasses import asdict
from slackwrap.ai.ollama_client import OllamaClient
from slackwrap.ai.prompts import (
    build_fun_facts_prompt, build_style_prompt, build_trajectory_prompt,
)
from slackwrap.ai.sampler import build_stats_summary
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters
from slackwrap.db import Database


def _hash_input(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _is_cached(db: Database, relationship_key: str, insight_type: str, input_hash: str) -> bool:
    row = db.execute(
        "SELECT id FROM ai_insights WHERE relationship_key = ? AND insight_type = ? AND input_hash = ?",
        (relationship_key, insight_type, input_hash),
    ).fetchone()
    return row is not None


def _store_insight(db: Database, relationship_key: str, insight_type: str,
                   model_name: str, input_hash: str, result: dict) -> None:
    db.execute(
        """INSERT INTO ai_insights (relationship_key, insight_type, model_name,
               input_hash, result_json, generated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (relationship_key, insight_type, model_name, input_hash,
         json.dumps(result), time.time()),
    )
    db.commit()


def generate_insights(db: Database, ollama: OllamaClient, you_id: int, them_id: int,
                      relationship_key: str, your_name: str, their_name: str) -> None:
    """Generate and cache all AI insights for a relationship."""
    if not ollama.is_available():
        return

    engine = AnalyticsEngine(db)
    filters = Filters()

    stats = build_stats_summary(engine, you_id=you_id, them_id=them_id)
    stats_hash = _hash_input(json.dumps(stats, sort_keys=True, default=str))

    # Fun facts
    if not _is_cached(db, relationship_key, "fun_facts", stats_hash):
        prompt = build_fun_facts_prompt(stats)
        result = ollama.chat_json(
            messages=[{"role": "user", "content": prompt}],
            schema={"type": "object", "properties": {
                "facts": {"type": "array", "items": {"type": "string"}}
            }},
        )
        _store_insight(db, relationship_key, "fun_facts", ollama.chat_model, stats_hash, result)

    # Communication style
    comm = engine.communication(you_id=you_id, them_id=them_id, filters=filters)
    comm_stats = {
        "your_avg_words": comm.your_avg_words,
        "their_avg_words": comm.their_avg_words,
        "your_emoji_total": comm.your_emoji_total,
        "their_emoji_total": comm.their_emoji_total,
        "your_reactions_given": comm.your_reactions_given,
        "their_reactions_given": comm.their_reactions_given,
    }
    style_hash = _hash_input(json.dumps(comm_stats, sort_keys=True))

    if not _is_cached(db, relationship_key, "style", style_hash):
        prompt = build_style_prompt(comm_stats, your_name=your_name, their_name=their_name)
        result = ollama.chat_json(
            messages=[{"role": "user", "content": prompt}],
            schema={"type": "object", "properties": {
                "your_style": {"type": "string"},
                "their_style": {"type": "string"},
                "comparison": {"type": "string"},
            }},
        )
        _store_insight(db, relationship_key, "style", ollama.chat_model, style_hash, result)

    # Relationship trajectory
    vol = engine.volume(you_id=you_id, them_id=them_id, filters=filters)
    streaks = engine.streaks(you_id=you_id, them_id=them_id, filters=filters)
    resp = engine.response_times(you_id=you_id, them_id=them_id, filters=filters)
    traj_data = {
        "monthly_volumes": vol.monthly_volumes,
        "longest_streak": streaks.longest_streak_days,
        "monthly_trend": resp.monthly_trend,
    }
    traj_hash = _hash_input(json.dumps(traj_data, sort_keys=True, default=str))

    if not _is_cached(db, relationship_key, "trajectory", traj_hash):
        prompt = build_trajectory_prompt(
            monthly_volumes=vol.monthly_volumes,
            streaks={"longest": streaks.longest_streak_days, "current": streaks.current_streak_days},
            response_trends=resp.monthly_trend,
        )
        result = ollama.chat_json(
            messages=[{"role": "user", "content": prompt}],
            schema={"type": "object", "properties": {
                "narrative": {"type": "string"},
                "phase": {"type": "string"},
                "peak_period": {"type": "string"},
            }},
        )
        _store_insight(db, relationship_key, "trajectory", ollama.chat_model, traj_hash, result)


def get_cached_insights(db: Database, relationship_key: str) -> list[dict]:
    """Retrieve all cached insights for a relationship."""
    rows = db.execute(
        "SELECT insight_type, result_json, generated_at FROM ai_insights WHERE relationship_key = ? ORDER BY generated_at DESC",
        (relationship_key,),
    ).fetchall()
    return [
        {
            "insight_type": r["insight_type"],
            "result": json.loads(r["result_json"]),
            "generated_at": r["generated_at"],
        }
        for r in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_insights.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/ai/insights.py tests/test_ai_insights.py
git commit -m "feat(v2): add batch insights — fun facts, style, trajectory with caching"
```

---

### Task 5: Chat Engine with Query Routing

**Files:**
- Create: `src/slackwrap/ai/chat_engine.py`
- Create: `tests/test_ai_chat_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai_chat_engine.py
from __future__ import annotations
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def chat_db(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(20):
        ts = 1700049600.0 + i * 86400
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"msg {i} about projects", created_at=ts)
    db.commit()
    return db, u1, u2


def test_chat_engine_creation(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine

    db, u1, u2 = chat_db
    mock_ollama = MagicMock()
    engine = ChatEngine(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    assert engine is not None


def test_chat_engine_responds(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine

    db, u1, u2 = chat_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.chat.return_value = "You exchanged 20 messages total."

    engine = ChatEngine(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    response = engine.ask("How many messages do we have?")
    assert len(response) > 0


def test_chat_engine_maintains_history(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine

    db, u1, u2 = chat_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    mock_ollama.chat.return_value = "Answer 1"

    engine = ChatEngine(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    engine.ask("First question")
    engine.ask("Follow up")

    assert len(engine.history) == 4  # 2 user + 2 assistant messages


def test_chat_engine_handles_unavailable_ollama(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine

    db, u1, u2 = chat_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = False

    engine = ChatEngine(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    response = engine.ask("anything")
    assert "ollama" in response.lower() or "not available" in response.lower()


def test_chat_engine_sql_execution(chat_db):
    from slackwrap.ai.chat_engine import ChatEngine

    db, u1, u2 = chat_db
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    # Simulate LLM returning a response with SQL
    mock_ollama.chat.return_value = "Let me check. Based on the data, you have 20 messages."

    engine = ChatEngine(db=db, ollama=mock_ollama, you_id=u1, them_id=u2,
                        your_name="Alice", their_name="Bob")
    response = engine.ask("How many total messages?")
    assert len(response) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ai_chat_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ChatEngine**

```python
# src/slackwrap/ai/chat_engine.py
from __future__ import annotations
import json
import re
from slackwrap.ai.ollama_client import OllamaClient
from slackwrap.ai.prompts import build_chat_system_prompt
from slackwrap.ai.sampler import build_stats_summary
from slackwrap.ai.insights import get_cached_insights
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.db import Database


class ChatEngine:
    """Interactive chat engine with query routing and session management."""

    def __init__(self, db: Database, ollama: OllamaClient,
                 you_id: int, them_id: int,
                 your_name: str = "You", their_name: str = "Them",
                 relationship_key: str | None = None):
        self.db = db
        self.ollama = ollama
        self.you_id = you_id
        self.them_id = them_id
        self.your_name = your_name
        self.their_name = their_name
        self.relationship_key = relationship_key or f"{you_id}:{them_id}"
        self.history: list[dict] = []
        self._system_prompt: str | None = None

    def _get_system_prompt(self) -> str:
        if self._system_prompt is None:
            engine = AnalyticsEngine(self.db)
            stats = build_stats_summary(engine, you_id=self.you_id, them_id=self.them_id)

            # Add cached AI insights to context
            cached = get_cached_insights(self.db, self.relationship_key)
            insights_context = ""
            for insight in cached:
                insights_context += f"\n{insight['insight_type']}: {json.dumps(insight['result'])}"

            base = build_chat_system_prompt(
                stats_summary=stats,
                your_name=self.your_name,
                their_name=self.their_name,
            )
            if insights_context:
                base += f"\n\nCached AI insights:{insights_context}"

            self._system_prompt = base
        return self._system_prompt

    def ask(self, question: str) -> str:
        """Ask a question and get a response. Maintains session history."""
        if not self.ollama.is_available():
            return "Ollama is not available. Please start it with: ollama serve"

        # Build messages with system prompt + history + new question
        messages = [{"role": "system", "content": self._get_system_prompt()}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": question})

        # Get LLM response
        response = self.ollama.chat(messages=messages, temperature=0.3)

        # Check if response contains SQL to execute
        response = self._execute_sql_in_response(response)

        # Update history
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": response})

        # Keep history manageable (last 20 messages)
        if len(self.history) > 20:
            self.history = self.history[-20:]

        return response

    def _execute_sql_in_response(self, response: str) -> str:
        """If the LLM included SQL queries, execute them and append results."""
        sql_pattern = re.compile(r"```sql\s*(.*?)\s*```", re.DOTALL)
        matches = sql_pattern.findall(response)

        for sql in matches:
            sql = sql.strip()
            # Safety: only allow SELECT
            if not sql.upper().startswith("SELECT"):
                continue
            try:
                cursor = self.db.execute(sql)
                rows = cursor.fetchall()
                if rows:
                    result_text = "\n".join(str(dict(r)) for r in rows[:20])
                    response += f"\n\nQuery result:\n{result_text}"
            except Exception as e:
                response += f"\n\n(Query error: {e})"

        return response

    def clear_history(self) -> None:
        self.history.clear()
        self._system_prompt = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ai_chat_engine.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/ai/chat_engine.py tests/test_ai_chat_engine.py
git commit -m "feat(v2): add ChatEngine — query routing, session history, SQL execution, system prompt"
```

---

### Task 6: Wire TUI Chat Screen

**Files:**
- Modify: `src/slackwrap/tui/screens/chat.py`
- Modify: `src/slackwrap/tui/app.py`

- [ ] **Step 1: Update TUI app to create ChatEngine**

Add to `SlackWrapApp.__init__` in `src/slackwrap/tui/app.py`:

```python
        self._chat_engine = None
```

Add a method to `SlackWrapApp`:

```python
    def get_chat_engine(self):
        if self._chat_engine is None and self.you_db_id and self.them_db_id:
            from slackwrap.ai.ollama_client import OllamaClient
            from slackwrap.ai.chat_engine import ChatEngine
            ollama = OllamaClient()
            self._chat_engine = ChatEngine(
                db=self.db, ollama=ollama,
                you_id=self.you_db_id, them_id=self.them_db_id,
                your_name="You", their_name=self.selected_user_name or "Them",
            )
        return self._chat_engine
```

- [ ] **Step 2: Update ChatScreen to use ChatEngine**

Replace `src/slackwrap/tui/screens/chat.py`:

```python
# src/slackwrap/tui/screens/chat.py
from __future__ import annotations
from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input, Header, Footer, RichLog
from textual.worker import get_current_worker


class ChatScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("  Chat with your data", id="chat-title")
        yield RichLog(id="chat-log", wrap=True, markup=True)
        yield Input(placeholder="Ask anything about your Slack history...", id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        engine = self.app.get_chat_engine()
        if engine is None:
            log.write("[dim]No data loaded. Sync first, then open chat.[/dim]")
        elif not engine.ollama.is_available():
            log.write("[dim]Ollama is not running. Chat requires a local LLM.[/dim]")
            log.write("[dim]Install: https://ollama.ai  |  Start: ollama serve[/dim]")
            log.write("")
            log.write("[dim]You can still use the dashboard and web view without Ollama.[/dim]")
        else:
            log.write("[bold]SlackWrap AI[/bold]: Ask me anything about your Slack history!")
            log.write("[dim]Try: How many messages did we exchange? / When was our busiest month? / How has my tone changed?[/dim]")
            log.write("")
        self.query_one("#chat-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return

        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold]You:[/bold] {query}")
        self.query_one("#chat-input", Input).value = ""

        engine = self.app.get_chat_engine()
        if engine is None or not engine.ollama.is_available():
            log.write("[dim]Chat unavailable. Ollama is not running.[/dim]")
            log.write("")
            return

        self._ask(query)

    @work(exclusive=True, thread=True)
    def _ask(self, query: str) -> None:
        worker = get_current_worker()
        engine = self.app.get_chat_engine()
        try:
            response = engine.ask(query)
            if not worker.is_cancelled:
                self.call_from_thread(self._show_response, response)
        except Exception as e:
            if not worker.is_cancelled:
                self.call_from_thread(self._show_response, f"Error: {e}")

    def _show_response(self, response: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[bold cyan]SlackWrap AI:[/bold cyan] {response}")
        log.write("")
```

- [ ] **Step 3: Run TUI tests to ensure no regressions**

Run: `python3 -m pytest tests/test_tui_chat.py tests/test_tui_app.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/slackwrap/tui/screens/chat.py src/slackwrap/tui/app.py
git commit -m "feat(v2): wire TUI ChatScreen to ChatEngine with Ollama integration"
```

---

### Task 7: Wire Web Chat

**Files:**
- Modify: `src/slackwrap/web/routes/chat.py`
- Modify: `src/slackwrap/web/templates/chat.html`

- [ ] **Step 1: Update chat route with POST endpoint**

```python
# src/slackwrap/web/routes/chat.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter()

# Session-level chat engine (per server lifetime)
_chat_engine = None


def _get_chat_engine(request: Request):
    global _chat_engine
    if _chat_engine is None:
        from slackwrap.ai.ollama_client import OllamaClient
        from slackwrap.ai.chat_engine import ChatEngine
        ollama = OllamaClient()
        _chat_engine = ChatEngine(
            db=request.app.state.db,
            ollama=ollama,
            you_id=request.app.state.you_id,
            them_id=request.app.state.them_id,
            your_name=request.app.state.your_name,
            their_name=request.app.state.their_name,
        )
    return _chat_engine


class ChatMessage(BaseModel):
    message: str


@router.get("", response_class=HTMLResponse)
def chat_page(request: Request):
    templates = request.app.state.templates
    engine = _get_chat_engine(request)
    ollama_available = engine.ollama.is_available() if engine else False
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "active_page": "chat",
        "your_name": request.app.state.your_name,
        "their_name": request.app.state.their_name,
        "ollama_available": ollama_available,
    })


@router.post("/ask")
def chat_ask(request: Request, msg: ChatMessage):
    engine = _get_chat_engine(request)
    if not engine or not engine.ollama.is_available():
        return {"response": "Ollama is not available. Start it with: ollama serve", "error": True}
    try:
        response = engine.ask(msg.message)
        return {"response": response, "error": False}
    except Exception as e:
        return {"response": f"Error: {e}", "error": True}
```

- [ ] **Step 2: Update chat template with interactive JS**

```html
<!-- src/slackwrap/web/templates/chat.html -->
{% extends "base.html" %}
{% block title %}SlackWrap — Chat{% endblock %}
{% block content %}
<div class="chat-container">
    <h1 style="margin-bottom: 16px;">Chat with your data</h1>
    <div class="chat-log" id="chat-log">
        {% if ollama_available %}
        <div class="chat-message">
            <div class="sender" style="color: var(--accent-light);">SlackWrap AI</div>
            <div class="body">Ask me anything about your Slack history with {{ their_name }}!</div>
        </div>
        {% else %}
        <div class="chat-message">
            <div class="sender" style="color: var(--accent-light);">SlackWrap</div>
            <div class="body">Chat requires Ollama to be running locally. Install: <a href="https://ollama.ai" style="color: var(--accent-light);">ollama.ai</a> | Start: <code>ollama serve</code></div>
        </div>
        {% endif %}
    </div>
    <div class="chat-input-bar">
        <input type="text" id="chat-input" placeholder="Ask anything about your Slack history..."
               {% if not ollama_available %}disabled{% endif %}
               onkeydown="if(event.key==='Enter')sendMessage()">
    </div>
</div>

<script>
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const log = document.getElementById('chat-log');
    const message = input.value.trim();
    if (!message) return;

    // Show user message
    log.innerHTML += `<div class="chat-message"><div class="sender" style="font-weight:600;">You</div><div class="body">${escapeHtml(message)}</div></div>`;
    input.value = '';
    input.disabled = true;
    log.scrollTop = log.scrollHeight;

    // Show thinking indicator
    const thinkingId = 'thinking-' + Date.now();
    log.innerHTML += `<div class="chat-message" id="${thinkingId}"><div class="sender" style="color: var(--accent-light);">SlackWrap AI</div><div class="body" style="color: var(--text-dim);">Thinking...</div></div>`;
    log.scrollTop = log.scrollHeight;

    try {
        const resp = await fetch('/chat/ask', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: message}),
        });
        const data = await resp.json();

        // Remove thinking indicator
        const thinking = document.getElementById(thinkingId);
        if (thinking) thinking.remove();

        // Show response
        log.innerHTML += `<div class="chat-message"><div class="sender" style="color: var(--accent-light);">SlackWrap AI</div><div class="body">${escapeHtml(data.response)}</div></div>`;
    } catch (e) {
        const thinking = document.getElementById(thinkingId);
        if (thinking) thinking.remove();
        log.innerHTML += `<div class="chat-message"><div class="sender" style="color: var(--warning);">Error</div><div class="body">${escapeHtml(e.message)}</div></div>`;
    }

    input.disabled = false;
    input.focus();
    log.scrollTop = log.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
</script>
{% endblock %}
```

- [ ] **Step 3: Run web tests to ensure no regressions**

Run: `python3 -m pytest tests/test_web_*.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/slackwrap/web/routes/chat.py src/slackwrap/web/templates/chat.html
git commit -m "feat(v2): wire web chat with interactive JS, POST endpoint, Ollama integration"
```

---

### Task 8: Update Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add ollama and sqlite-vec dependencies**

```toml
[project]
name = "slackwrap"
version = "2.0.0"
description = "Your Slack year in review — huddle and message analytics"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
dependencies = [
    "requests>=2.31.0",
    "python-dotenv>=1.0.0",
    "textual>=0.50.0",
    "fastapi>=0.100.0",
    "uvicorn>=0.20.0",
    "jinja2>=3.1.0",
]

[project.optional-dependencies]
ai = [
    "ollama>=0.4.0",
    "sqlite-vec>=0.1.0",
]
dev = [
    "pytest>=8.0.0",
    "httpx>=0.24.0",
    "ollama>=0.4.0",
]

[project.scripts]
slackwrap = "slackwrap.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest tests/ -v --ignore=tests/test_cache.py --ignore=tests/test_main.py --ignore=tests/test_message_analytics.py --ignore=tests/test_report.py --ignore=tests/test_slack_client.py`
Expected: All v2 tests PASS

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(v2): add ollama and sqlite-vec as optional AI dependencies"
```

---

## Plan Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | OllamaClient — connection check, chat, JSON, embeddings | 7 |
| 2 | Message sampler — stratified sampling, windows, stats summary | 5 |
| 3 | Prompt templates — tone, style, fun facts, trajectory, chat, SQL | 5 |
| 4 | Batch insights — generate and cache AI insights with dedup | 4 |
| 5 | ChatEngine — query routing, session history, SQL execution | 5 |
| 6 | Wire TUI ChatScreen to ChatEngine | 0 (regression) |
| 7 | Wire web chat with interactive JS + POST endpoint | 0 (regression) |
| 8 | Dependencies — ollama, sqlite-vec as optional | 0 |

**Total: 8 tasks, 26 tests, ~8 commits**

After this plan, SlackWrap v2 is feature-complete: sync data, view analytics in TUI dashboard or web browser, get AI-powered insights, and chat with your data through both interfaces.
