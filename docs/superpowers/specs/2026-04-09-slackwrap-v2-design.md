# SlackWrap v2 — Design Spec

## Product Vision

SlackWrap is a data exploration platform for your Slack history. It tells the story of your relationship with a colleague through a curated Wrapped-style narrative, but more importantly, it lets you ask anything about your Slack data — drill into any metric, explore patterns, and get AI-powered insights.

Launch it in the terminal, pick a person, and explore — through a Textual TUI, a rich web dashboard, or a conversational chat interface backed by a local LLM.

**Core principle:** Sync once, query forever. All analytics run against local SQLite. The Slack API is only touched during explicit sync operations.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                      SlackWrap                        │
│                                                       │
│  ┌───────────┐    ┌────────────┐    ┌──────────────┐ │
│  │  Textual  │    │  FastAPI   │    │   Slack      │ │
│  │   TUI     │    │  Web View  │    │   Sync       │ │
│  │           │    │            │    │   Engine     │ │
│  └─────┬─────┘    └─────┬──────┘    └──────┬───────┘ │
│        │                │                   │        │
│        ▼                ▼                   ▼        │
│  ┌────────────────────────────────────────────────┐  │
│  │              Analytics Engine                   │  │
│  │  (General-purpose query layer over SQLite)      │  │
│  └──────────────────┬─────────────────────────────┘  │
│                     │                                │
│        ┌────────────┼────────────┐                   │
│        ▼            ▼            ▼                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐         │
│  │  SQLite  │ │sqlite-vec│ │   Ollama     │         │
│  │  (data)  │ │(vectors) │ │   (local)    │         │
│  └──────────┘ └──────────┘ └──────────────┘         │
└──────────────────────────────────────────────────────┘
```

### Four Layers

1. **Slack Sync Engine** — fetches data from Slack API, writes into SQLite. Decoupled from all other layers. Runs only on explicit sync.
2. **SQLite + sqlite-vec** — normalized schema, vector embeddings, pre-computed rollups, AI insight cache. Single file at `~/.slackwrap/data.db`.
3. **Analytics Engine** — general-purpose query layer. Every view (Wrapped story, explore, deep dives, chat) is a consumer of this engine. Not a fixed set of computations — a queryable API.
4. **Presentation** — Textual TUI (control plane + quick stats + chat) and FastAPI web server (Wrapped story, explorer, deep dives, chat sidebar).

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| TUI | Textual | Python-native, CSS-like styling, async, rich widgets |
| Web backend | FastAPI | Lightweight, async, easy to serve alongside TUI |
| Web frontend | Jinja2 + Chart.js + vanilla JS | No build step, no npm, ships with pip install |
| Database | SQLite | Zero dependency, single file, fast analytics |
| Vector search | sqlite-vec | SQLite extension, no separate service |
| Embeddings | Ollama (nomic-embed-text) | Local, same runtime as LLM |
| LLM | Ollama (llama3 / mistral) | Local, no data leaves machine, HTTP API |
| Slack API | requests + User OAuth Token | Already proven in v1 |

## Sync Engine

### Principle: Sync Once, Query Forever

Analytics never touch the Slack API. Every query, chart, AI insight, and chat answer runs against local SQLite. The only time we talk to Slack is during an explicit sync.

### Sync Phases

**Phase 1: Initial Sync (first run, slowest)**
- Fetch all users (paginated, store locally)
- Fetch all channels + DMs
- For each relevant channel:
  - Fetch full message history
  - Fetch thread replies (batched, not one-by-one)
  - Fetch pins, bookmarks, files
- Fetch user profiles (batch) — timezone, title, start_date, status
- Fetch reactions.list per user
- Record sync cursors per channel in `sync_state`

**Phase 2: Delta Sync (subsequent runs, fast)**
- Check `sync_state` for each channel's last cursor
- Fetch only messages newer than last synced timestamp
- Fetch only new thread replies for updated threads
- Upsert into SQLite (`ON CONFLICT UPDATE`)
- Update sync cursors

**Phase 3: Post-Sync Compute (runs after sync)**
- Rebuild rollup tables (`weekly_stats`, `monthly_stats`)
- Compute embeddings for new messages only (incremental)
- Re-generate AI insights if data changed (compare `input_hash`)

### Sync Design Decisions

| Decision | Rationale |
|----------|-----------|
| Sync is decoupled from viewing | Can sync in background, dashboard opens instantly from local data |
| Adaptive rate budget | Track per-tier budgets across full sync. Show time estimate upfront: "I need 200 Tier 3 calls, ~5 min" |
| Batch where possible | `users.conversations` for both users (2 calls) then intersect — replaces current N-call membership check |
| Thread reply pipeline | Collect all thread parents first, fetch replies in pipeline instead of blocking one-by-one |
| Sync only selected relationships | Don't sync whole workspace. User selects a person, sync that DM + shared channels. Add more people over time |
| Resumable sync | If interrupted, picks up from last cursor. Doesn't restart |
| Sync freshness indicator | Dashboard shows "Last synced: 2h ago" with refresh keybind |

## Data Sources — Slack APIs

### Existing (already used in v1)

- `auth.test` — verify token, get user ID, workspace name
- `users.list` — search/list users
- `users.info` — user profiles (extract more: timezone, locale, tz_offset)
- `conversations.list` — list channels/DMs
- `conversations.history` — fetch messages (paginated)
- `conversations.replies` — fetch thread replies
- `conversations.members` — check channel membership

### New — No New Scopes

| API | Data | Insight |
|-----|------|---------|
| `conversations.info` | Channel metadata, creation date, topic, member count | "Your DM has been open since Jan 2023" |
| `users.conversations` | All channels a user is in | Efficient shared channel discovery (2 calls instead of N) |
| `chat.getPermalink` | Deep links to specific messages | Clickable highlights in web view |
| `users.info` (extract more) | Timezone, locale, tz_offset | "Your overlap window is 10am-2pm PST" |

### New — New Scopes Required

| API | Scope | Insight |
|-----|-------|---------|
| `users.profile.get` | `users.profile:read` | Start date, title, status — "Colleagues for 2.3 years" |
| `files.list` + `files.info` | `files:read` | File sharing breakdown by type/size — "34 images, 12 PDFs" |
| `reactions.list` | `reactions:read` | Complete cross-channel reaction profile |
| `search.messages` | `search:read` | Cross-workspace mentions, interactions outside the DM |
| `pins.list` | `pins:read` | Pinned messages as relationship highlights |
| `emoji.list` | `emoji:read` | Render custom workspace emoji in web view |
| `team.info` | `team:read` | Workspace branding — "Your [WorkspaceName] Wrapped" |
| `bookmarks.list` | `bookmarks:read` | Shared resources in channels |
| `dnd.info` | `dnd:read` | DND schedule context for response time analysis |

### Full Scope List

Existing: `channels:history`, `groups:history`, `im:history`, `users:read`, `channels:read`, `groups:read`, `im:read`

New: `users.profile:read`, `files:read`, `reactions:read`, `search:read`, `pins:read`, `emoji:read`, `team:read`, `bookmarks:read`, `dnd:read`

## SQLite Schema

### Core Tables

```sql
-- Users
users (
  id INTEGER PRIMARY KEY,
  slack_id TEXT UNIQUE NOT NULL,
  name TEXT,
  display_name TEXT,
  real_name TEXT,
  is_bot BOOLEAN DEFAULT FALSE,
  timezone TEXT,
  tz_offset INTEGER,
  title TEXT,
  start_date TEXT,
  status_text TEXT,
  status_emoji TEXT,
  locale TEXT,
  avatar_url TEXT,
  synced_at REAL
)

-- Channels
channels (
  id INTEGER PRIMARY KEY,
  slack_id TEXT UNIQUE NOT NULL,
  name TEXT,
  type TEXT NOT NULL,  -- 'dm', 'channel', 'group', 'mpim'
  created_at REAL,
  topic TEXT,
  purpose TEXT,
  num_members INTEGER,
  is_archived BOOLEAN DEFAULT FALSE,
  synced_at REAL
)

-- Messages
messages (
  id INTEGER PRIMARY KEY,
  channel_id INTEGER NOT NULL REFERENCES channels(id),
  user_id INTEGER REFERENCES users(id),
  slack_ts TEXT NOT NULL,
  text TEXT,
  subtype TEXT,
  thread_ts TEXT,
  reply_count INTEGER DEFAULT 0,
  files_count INTEGER DEFAULT 0,
  is_thread_reply BOOLEAN GENERATED ALWAYS AS (thread_ts IS NOT NULL AND thread_ts != slack_ts) STORED,
  created_at REAL NOT NULL,
  UNIQUE(channel_id, slack_ts)
)

-- Reactions
reactions (
  id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES messages(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  emoji_name TEXT NOT NULL
)

-- Huddles (extracted at sync time)
huddles (
  id INTEGER PRIMARY KEY,
  channel_id INTEGER NOT NULL REFERENCES channels(id),
  created_by_user_id INTEGER REFERENCES users(id),
  started_at REAL NOT NULL,
  ended_at REAL NOT NULL,
  duration_seconds INTEGER GENERATED ALWAYS AS (CAST(ended_at - started_at AS INTEGER)) STORED,
  participant_ids TEXT NOT NULL  -- JSON array of user IDs
)

-- Files
files (
  id INTEGER PRIMARY KEY,
  channel_id INTEGER REFERENCES channels(id),
  user_id INTEGER REFERENCES users(id),
  slack_file_id TEXT UNIQUE NOT NULL,
  name TEXT,
  filetype TEXT,
  size_bytes INTEGER,
  created_at REAL
)

-- Pins
pins (
  id INTEGER PRIMARY KEY,
  channel_id INTEGER NOT NULL REFERENCES channels(id),
  user_id INTEGER REFERENCES users(id),
  message_ts TEXT,
  pinned_at REAL
)

-- Cross-channel mentions (from search.messages)
mentions (
  id INTEGER PRIMARY KEY,
  channel_id INTEGER REFERENCES channels(id),
  from_user_id INTEGER REFERENCES users(id),
  mentioned_user_id INTEGER REFERENCES users(id),
  message_ts TEXT,
  context_text TEXT
)

-- Sync state per channel
sync_state (
  channel_id INTEGER PRIMARY KEY REFERENCES channels(id),
  last_synced_ts TEXT,
  last_synced_at REAL,
  status TEXT DEFAULT 'pending'  -- 'pending', 'syncing', 'complete', 'error'
)
```

### Rollup Tables (Pre-computed at Sync Time)

```sql
-- Weekly rollups for instant stat lookups
weekly_stats (
  id INTEGER PRIMARY KEY,
  relationship_key TEXT NOT NULL,  -- 'user1_id:user2_id'
  week_start TEXT NOT NULL,
  message_count INTEGER,
  your_count INTEGER,
  their_count INTEGER,
  avg_response_seconds REAL,
  huddle_count INTEGER,
  huddle_seconds INTEGER,
  avg_word_count_you REAL,
  avg_word_count_them REAL,
  emoji_count INTEGER,
  reaction_count INTEGER,
  UNIQUE(relationship_key, week_start)
)

-- Monthly rollups
monthly_stats (
  id INTEGER PRIMARY KEY,
  relationship_key TEXT NOT NULL,
  month TEXT NOT NULL,
  message_count INTEGER,
  your_count INTEGER,
  their_count INTEGER,
  avg_response_seconds REAL,
  huddle_count INTEGER,
  huddle_seconds INTEGER,
  avg_word_count_you REAL,
  avg_word_count_them REAL,
  emoji_count INTEGER,
  reaction_count INTEGER,
  tone_label TEXT,  -- from AI analysis
  UNIQUE(relationship_key, month)
)
```

### Vector Search (sqlite-vec)

```sql
-- Embeddings for semantic search
message_embeddings (
  message_id INTEGER PRIMARY KEY REFERENCES messages(id),
  embedding FLOAT[384]  -- nomic-embed-text dimension
)
```

Conversation windows (10-message sliding windows with overlap) are embedded, not isolated messages. This preserves conversational context for semantic search.

Embeddings computed at sync time, incrementally — only new messages get embedded.

### AI Insight Cache

```sql
ai_insights (
  id INTEGER PRIMARY KEY,
  relationship_key TEXT NOT NULL,
  insight_type TEXT NOT NULL,  -- 'tone', 'style', 'trajectory', 'highlights', 'fun_facts'
  model_name TEXT,
  input_hash TEXT,  -- hash of input data, skip regeneration if unchanged
  result_json TEXT NOT NULL,
  generated_at REAL
)
```

### Indexes

```sql
CREATE INDEX idx_messages_channel_created ON messages(channel_id, created_at);
CREATE INDEX idx_messages_user_channel ON messages(user_id, channel_id);
CREATE INDEX idx_messages_thread ON messages(channel_id, thread_ts);
CREATE INDEX idx_reactions_message ON reactions(message_id);
CREATE INDEX idx_reactions_user ON reactions(user_id);
CREATE INDEX idx_huddles_channel ON huddles(channel_id);
CREATE INDEX idx_files_user ON files(user_id);
CREATE INDEX idx_weekly_stats_lookup ON weekly_stats(relationship_key, week_start);
CREATE INDEX idx_monthly_stats_lookup ON monthly_stats(relationship_key, month);
```

### FTS5 (Full-Text Search)

```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(text, content=messages, content_rowid=id);
```

Enables fast text search: `SELECT * FROM messages_fts WHERE messages_fts MATCH 'deployment'`

## Analytics Engine

### Design: General-Purpose Query Layer

The analytics engine is not a fixed set of computations. It's a queryable API that any view can consume. The Wrapped story, explorer, deep dives, and chat are all clients of the same engine.

```python
class AnalyticsEngine:
    """General-purpose query layer over SlackWrap SQLite data."""

    # Core queries
    def messages(self, filters: Filters) -> QueryResult
    def response_times(self, filters: Filters) -> QueryResult
    def huddles(self, filters: Filters) -> QueryResult
    def reactions(self, filters: Filters) -> QueryResult
    def files(self, filters: Filters) -> QueryResult

    # Aggregations
    def aggregate(self, metric: str, group_by: str, filters: Filters) -> QueryResult
    def trends(self, period: str, metric: str, filters: Filters) -> QueryResult
    def heatmap(self, x_axis: str, y_axis: str, filters: Filters) -> HeatmapResult

    # Search
    def text_search(self, query: str, filters: Filters) -> list[Message]
    def semantic_search(self, query: str, limit: int) -> list[Message]

    # Pre-computed
    def weekly_rollup(self, relationship_key: str) -> list[WeeklyStats]
    def monthly_rollup(self, relationship_key: str) -> list[MonthlyStats]

    # Raw SQL (for LLM-generated queries)
    def raw_sql(self, query: str) -> QueryResult

@dataclass
class Filters:
    relationship_key: str | None = None
    user_id: str | None = None
    channel_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    day_of_week: str | None = None
    hour: int | None = None
    subtype: str | None = None
    has_reactions: bool | None = None
    has_files: bool | None = None
    in_thread: bool | None = None
```

### Analytics — What We Compute

All analytics from v1 are preserved. New analytics are added. Everything is queryable, not just pre-rendered.

#### Carried Over from v1 (proven valuable)

**Volume & Activity:**
- Total message count + per-user split with percentages
- Messages per week rate
- Busiest day ever (date + count)
- Day-of-week breakdown
- Hour-of-day breakdown
- Monthly volume breakdown

**Huddles:**
- Total huddle time, count, average, median, longest, shortest
- Who starts huddles (% split)
- Huddle weekday breakdown
- Huddle-to-message ratio, messages per huddle

**Response Time:**
- Turn-based response time (collapse consecutive same-user messages into turns)
- Median + average per user
- Skip gaps > 4 hours (overnight, weekends)
- Response time by hour (fastest/slowest hour)

**Threads:**
- Top-level vs in-thread message breakdown
- Who starts threads (thread parent count per user)

**Communication Style:**
- Average word count per user (strips code blocks, mentions, links, emoji)
- Most used words (top 10, 3+ letter words)
- Emoji in messages (per user count + top 5)
- Reactions given (per user + top 5)
- Links & files shared per user

**Streaks & Gaps:**
- Longest conversation streak with date range
- Current streak
- Longest silence (dead zone) with date range

**Bookends:**
- First and last message with text preview

**Trends:**
- 30-day rolling comparison with % change
- Year-over-year with daily rate normalization for partial months

#### New in v2

**Enhanced Activity:**
- Message length distribution (histogram: short/medium/long)
- Reply chain depth (deepest thread, average depth)
- Conversation initiation (who sends first message of the day)
- Active days count ("You talked on 240 out of 365 days")
- Weekend vs weekday split
- Conversation density (messages per active day)
- Monthly message rank ("March was #1, November was quietest")

**Patterns & Heatmaps:**
- Hour x day-of-week activity heatmap (GitHub contribution graph style)
- Peak collaboration windows (hours where both users active + fast responses)
- Response time trend over months (getting faster or slower?)
- Timezone overlap window analysis

**Relationship Signals:**
- Reciprocity index (effort ratio — messages, words, reactions normalized)
- Emoji diversity score (unique emoji count — connoisseur vs thumbsup-only)
- File sharing breakdown by type and size
- Pinned message highlights
- Cross-channel mention frequency
- Shared channel activity distribution

**Enriched Context:**
- Workspace branding (name, icon from team.info)
- Colleague tenure ("Colleagues since [start_date]")
- DND-aware response time context
- Clickable message permalinks in all highlights

## AI Layer

### Runtime: Ollama (Local)

- Runs locally, no data leaves the machine
- HTTP API at `localhost:11434`
- SlackWrap detects if Ollama is running
- Graceful degradation: full dashboard with raw stats if Ollama unavailable

### Batch Insights (Generated at Sync Time)

| Insight Type | Input to LLM | Output |
|-------------|-------------|--------|
| Tone evolution | Message samples per month (your messages only) | Tone labels per month + narrative |
| Communication style profile | Word counts, emoji, response times, lengths | Style description per user |
| Relationship trajectory | Monthly volume trends, streak data, response trends | Narrative arc of the relationship |
| Highlights narrative | Most-reacted messages, longest threads, busiest days | Natural language highlight descriptions |
| Behavioral patterns | Heatmap data, DND schedules, timezone info | Pattern descriptions ("morning person vs night owl") |
| Fun facts | All aggregated stats | Personalized observations and projections |

**Message sampling strategy:** ~20 messages per month per user, stratified by time of day and message length variety. Keeps context windows manageable.

**Structured output:** LLM returns JSON with specific fields (tone_label, confidence, narrative_text). Renderable in both TUI and web view.

**Cached:** AI insights stored in `ai_insights` table with `input_hash`. Skip regeneration if data hasn't changed.

### Chat Layer (Interactive Q&A)

Available in both TUI (keybind `c`) and web view (sidebar).

#### Query Router

```
User question
     |
     v
 Query Router (classifies intent)
     |
     |--- Stat question ---------> Pre-computed rollup lookup (<10ms)
     |    "How many messages?"
     |
     |--- Time-range question ---> SQL generation against SQLite (<50ms)
     |    "What happened in Nov?"
     |
     |--- Content question ------> sqlite-vec semantic search (<200ms)
     |    "What were we arguing      + message chunk retrieval
     |     about?"
     |
     |--- Tone/pattern question -> Pre-computed AI insights lookup (<10ms)
     |    "How's my tone changed?"
     |
     |--- Complex question ------> Combination of above + LLM synthesis
          "Compare my Nov and Dec
           communication style"
```

#### How It Works

1. User asks a question in natural language
2. Query router classifies intent (stat / time-range / content / tone / complex)
3. For stat questions: direct lookup against rollup tables, narrated by LLM
4. For data questions: LLM generates SQL, engine executes it, LLM narrates results
5. For content questions: semantic search via sqlite-vec retrieves relevant message chunks, LLM synthesizes
6. For tone/pattern questions: lookup cached AI insights, LLM contextualizes
7. Session-aware: conversation history maintained so follow-ups work ("What about compared to last year?")

#### LLM System Prompt Context

The chat LLM receives:
- Pre-computed stats summary (key metrics for the relationship)
- SQLite schema description (so it can generate valid SQL)
- Available rollup data (so it knows what's queryable)
- Current AI insights (tone, style, trajectory)
- Session history (for follow-up context)

It does NOT receive raw message dumps. It queries for specific data as needed.

## Presentation Layer

### Textual TUI

The TUI is the control plane — sync management, quick stats, and a lightweight chat mode.

**Screens:**

1. **Search & Select** — "Who do you want to wrap?" Type-ahead search, select from results.
2. **Sync Progress** — Progress bars for message fetch, embedding computation, AI insight generation. Resumable.
3. **Dashboard** — Key stats at a glance: sparklines, stat cards, recent activity. Keybinds: `w` open web, `c` chat, `s` sync, `q` quit, `/` switch person.
4. **Chat Mode** — Inline chat in the terminal. Question → answer loop with session context.

### Web View (FastAPI + Jinja2 + Chart.js)

Triggered from TUI via `w` keybind. Spins up local server on an available port, opens browser.

**Four modes accessible via left nav:**

#### 1. Story (Wrapped Narrative)

Scroll-driven, card-by-card reveal — the curated "Spotify Wrapped" experience.

**Chapters:**

- **Chapter 1: "Your Year Together"** — timeline overview, total messages/huddles/files, workspace branding, colleague tenure
- **Chapter 2: "By the Numbers"** — message volume, huddle time, file sharing, thread activity, active days
- **Chapter 3: "Your Rhythm"** — hour x day-of-week heatmap, timezone overlap, peak collaboration windows, DND context
- **Chapter 4: "How You Communicate"** — AI tone analysis over time, style profiles, word counts, emoji evolution, most used words, favorite reactions
- **Chapter 5: "Highlights"** — most-reacted messages (with permalinks), longest threads, pinned messages, busiest day story, first & last message
- **Chapter 6: "Your Streaks"** — longest streak, current streak, longest silence, milestones ("Your 1000th message")
- **Chapter 7: "Trends"** — 30-day comparison, YoY, AI relationship trajectory narrative, monthly sparkline
- **Chapter 8: "Fun Facts"** — AI-generated personalized observations, projections, behavioral patterns

#### 2. Explore (Interactive Dashboard)

Filterable charts and tables. Date range picker, user filter, channel filter. Every chart is clickable and drillable.

- Message volume over time (bar chart, filterable by period)
- Activity heatmap (hour x day)
- Response time trends (line chart over months)
- Communication style comparison (radar chart)
- Emoji & reaction explorer
- File sharing timeline
- Any metric can be grouped by: day, week, month, hour, day-of-week, channel

#### 3. Deep Dives

Pre-built analytical views, each its own page:

- **Response Time Analysis** — trends, by hour, by day, comparison
- **Communication Style** — word clouds, tone evolution, message length distribution
- **Activity Patterns** — heatmaps, peak hours, weekend vs weekday
- **Files & Sharing** — type breakdown, size totals, timeline
- **Reactions & Emoji** — diversity scores, favorites, trends
- **Trends & Forecasts** — monthly, quarterly, YoY, AI projections

#### 4. Chat

Full-width chat interface. Natural language queries with rendered results (tables, charts inline in chat responses). Session history in sidebar.

## Graceful Degradation

| Component | If Missing | Experience |
|-----------|-----------|------------|
| Ollama | Not installed | Full dashboard + explore + deep dives with raw stats. No AI insights, no tone analysis, no chat. Prompt to install. |
| sqlite-vec | Not installed | Everything except semantic search in chat. Stat/SQL queries still work. Text search via FTS5 still works. |
| New Slack scopes | Not granted | Core analytics with existing scopes. Missing features show "Grant [scope] to unlock [feature]" |
| Web browser | Not available | TUI dashboard + TUI chat. Full experience in terminal. |

## Dependencies

### Required
- `textual` — TUI framework
- `fastapi` + `uvicorn` — web server
- `jinja2` — HTML templates
- `requests` — Slack API calls
- `python-dotenv` — env config

### Optional (enhance experience)
- `sqlite-vec` — vector search for semantic chat queries
- `ollama` (external) — local LLM for AI insights and chat

### Dev
- `pytest` — testing

### Ollama Model Defaults
- **LLM:** `llama3.1:8b` (default) — good balance of quality and speed on consumer hardware. User can override in `config.toml`.
- **Embeddings:** `nomic-embed-text` — 384-dimension, fast, good semantic quality.
- **Minimum hardware:** 8GB RAM for 8b models. 16GB recommended for better throughput.

## Data Location

All data stored in `~/.slackwrap/`:
- `data.db` — SQLite database (messages, stats, embeddings, AI cache)
- `config.toml` — user preferences (default model, web port, theme)

No data in project directory. No data sent to external servers. Only network calls are to Slack API (during sync) and Ollama (localhost, during AI operations).
