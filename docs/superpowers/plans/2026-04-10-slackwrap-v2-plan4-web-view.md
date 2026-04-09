# SlackWrap v2 — Plan 4: Web View

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web dashboard served by FastAPI that presents the Wrapped story, interactive explorer, deep dives, and a chat stub — triggered from the TUI via the `w` keybind.

**Architecture:** FastAPI app with Jinja2 templates and Chart.js for client-side charts. A `WebServer` class wraps uvicorn in a daemon thread so it runs alongside the Textual TUI. The FastAPI app receives a `Database` reference and uses the `AnalyticsEngine` to serve data. Templates are server-rendered HTML with embedded JSON data for Chart.js. The four modes (Story, Explore, Deep Dives, Chat) are separate pages linked via a left nav.

**Tech Stack:** FastAPI, uvicorn, Jinja2, Chart.js (CDN), Python 3.10+

**Spec:** `docs/superpowers/specs/2026-04-09-slackwrap-v2-design.md` (Web View section)

**Depends on:** Plans 1-3 (Data Layer, Analytics Engine, TUI)

---

## File Structure

```
src/slackwrap/
  web/
    __init__.py
    server.py           # WebServer class — starts/stops uvicorn in background thread
    app.py              # FastAPI app factory — creates app with routes, templates, DB reference
    routes/
      __init__.py
      story.py          # /story — Wrapped narrative page
      explore.py        # /explore — interactive dashboard with charts
      deep_dives.py     # /deep-dives/* — analytical views
      chat.py           # /chat — stub until Plan 5
      api.py            # /api/* — JSON endpoints for AJAX chart data
    templates/
      base.html         # Base template with nav, Chart.js CDN, dark theme CSS
      story.html        # Wrapped story — scroll-driven chapters
      explore.html      # Explorer — filterable charts
      deep_dives/
        index.html      # Deep dives index
        response_time.html
        communication.html
        activity.html
      chat.html         # Chat stub
    static/
      style.css         # Custom CSS (dark theme, cards, animations)
  tui/
    app.py              # MODIFY: wire up action_open_web to launch WebServer
    screens/
      dashboard.py      # MODIFY: wire up action_open_web
tests/
  test_web_server.py    # Server start/stop tests
  test_web_app.py       # FastAPI route tests using TestClient
  test_web_api.py       # JSON API endpoint tests
```

**Note on templates:** Jinja2 templates contain HTML/CSS/JS. The plan provides complete template code for each page. Chart.js is loaded from CDN — no npm or build step.

---

### Task 1: Web Server Wrapper

**Files:**
- Create: `src/slackwrap/web/__init__.py`
- Create: `src/slackwrap/web/server.py`
- Create: `tests/test_web_server.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_web_server.py
from __future__ import annotations
import time
import requests
from unittest.mock import MagicMock


def test_web_server_starts_and_stops():
    from slackwrap.web.server import WebServer
    from slackwrap.db import Database

    db = Database(":memory:")
    db.initialize()
    server = WebServer(db=db, you_id=1, them_id=2, your_name="You", their_name="Them")
    server.start()
    time.sleep(0.5)

    try:
        resp = requests.get(f"http://127.0.0.1:{server.port}/health", timeout=2)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        server.stop()
        db.close()


def test_web_server_picks_available_port():
    from slackwrap.web.server import WebServer
    from slackwrap.db import Database

    db = Database(":memory:")
    db.initialize()
    server = WebServer(db=db, you_id=1, them_id=2, your_name="You", their_name="Them")
    assert server.port > 0
    db.close()


def test_web_server_returns_url():
    from slackwrap.web.server import WebServer
    from slackwrap.db import Database

    db = Database(":memory:")
    db.initialize()
    server = WebServer(db=db, you_id=1, them_id=2, your_name="You", their_name="Them")
    assert f"http://127.0.0.1:{server.port}" in server.url
    db.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_web_server.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement WebServer**

```python
# src/slackwrap/web/__init__.py
```

```python
# src/slackwrap/web/server.py
from __future__ import annotations
import socket
import threading
import uvicorn
from slackwrap.db import Database
from slackwrap.web.app import create_app


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WebServer:
    def __init__(self, db: Database, you_id: int, them_id: int,
                 your_name: str = "You", their_name: str = "Them",
                 host: str = "127.0.0.1", port: int | None = None):
        self.host = host
        self.port = port or _find_free_port()
        self.db = db
        self.you_id = you_id
        self.them_id = them_id
        self.your_name = your_name
        self.their_name = their_name
        self._app = create_app(
            db=db, you_id=you_id, them_id=them_id,
            your_name=your_name, their_name=their_name,
        )
        self._config = uvicorn.Config(
            self._app, host=self.host, port=self.port,
            log_level="warning",
        )
        self._server = uvicorn.Server(self._config)
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
```

- [ ] **Step 4: Create minimal FastAPI app for server to work**

```python
# src/slackwrap/web/app.py
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slackwrap.db import Database

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app(db: Database, you_id: int, them_id: int,
               your_name: str = "You", their_name: str = "Them") -> FastAPI:
    app = FastAPI(title="SlackWrap")

    # Store references for route handlers
    app.state.db = db
    app.state.you_id = you_id
    app.state.them_id = them_id
    app.state.your_name = your_name
    app.state.their_name = their_name

    # Templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates

    # Static files
    STATIC_DIR.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return {"message": "SlackWrap Web View", "status": "ok"}

    # Register route modules
    from slackwrap.web.routes import story, explore, deep_dives, chat, api
    app.include_router(story.router, prefix="/story", tags=["story"])
    app.include_router(explore.router, prefix="/explore", tags=["explore"])
    app.include_router(deep_dives.router, prefix="/deep-dives", tags=["deep-dives"])
    app.include_router(chat.router, prefix="/chat", tags=["chat"])
    app.include_router(api.router, prefix="/api", tags=["api"])

    return app
```

Create route stubs so the app can import them:

```python
# src/slackwrap/web/routes/__init__.py
```

```python
# src/slackwrap/web/routes/story.py
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("")
def story_page(request: Request):
    return {"page": "story", "status": "placeholder"}
```

```python
# src/slackwrap/web/routes/explore.py
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("")
def explore_page(request: Request):
    return {"page": "explore", "status": "placeholder"}
```

```python
# src/slackwrap/web/routes/deep_dives.py
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("")
def deep_dives_index(request: Request):
    return {"page": "deep_dives", "status": "placeholder"}
```

```python
# src/slackwrap/web/routes/chat.py
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("")
def chat_page(request: Request):
    return {"page": "chat", "status": "placeholder"}
```

```python
# src/slackwrap/web/routes/api.py
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/health")
def api_health():
    return {"status": "ok"}
```

Create empty static CSS:

```css
/* src/slackwrap/web/static/style.css */
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_web_server.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/slackwrap/web/ tests/test_web_server.py
git commit -m "feat(v2): add WebServer with FastAPI, uvicorn background thread, route stubs"
```

---

### Task 2: Base Template and Static Assets

**Files:**
- Create: `src/slackwrap/web/templates/base.html`
- Create: `src/slackwrap/web/static/style.css`

- [ ] **Step 1: Create the base HTML template**

```html
<!-- src/slackwrap/web/templates/base.html -->
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}SlackWrap{% endblock %}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav class="sidebar">
        <div class="nav-brand">
            <h2>SlackWrap</h2>
            <p class="nav-subtitle">{{ your_name }} &amp; {{ their_name }}</p>
        </div>
        <ul class="nav-links">
            <li><a href="/story" class="{% if active_page == 'story' %}active{% endif %}">Story</a></li>
            <li><a href="/explore" class="{% if active_page == 'explore' %}active{% endif %}">Explore</a></li>
            <li><a href="/deep-dives" class="{% if active_page == 'deep-dives' %}active{% endif %}">Deep Dives</a></li>
            <li><a href="/chat" class="{% if active_page == 'chat' %}active{% endif %}">Chat</a></li>
        </ul>
    </nav>
    <main class="content">
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

- [ ] **Step 2: Create the dark theme CSS**

```css
/* src/slackwrap/web/static/style.css */

:root {
    --bg: #0f0f13;
    --bg-card: #1a1a24;
    --bg-card-hover: #22222e;
    --bg-sidebar: #13131a;
    --text: #e4e4e8;
    --text-muted: #8b8b9e;
    --text-dim: #5a5a6e;
    --accent: #6c5ce7;
    --accent-light: #a29bfe;
    --success: #00b894;
    --warning: #fdcb6e;
    --border: #2d2d3a;
    --radius: 12px;
    --shadow: 0 4px 24px rgba(0,0,0,0.3);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    display: flex;
    min-height: 100vh;
}

/* Sidebar */
.sidebar {
    width: 220px;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    padding: 24px 16px;
    position: fixed;
    height: 100vh;
    overflow-y: auto;
}

.nav-brand h2 { font-size: 1.3rem; color: var(--accent-light); }
.nav-subtitle { font-size: 0.8rem; color: var(--text-muted); margin-top: 4px; }

.nav-links { list-style: none; margin-top: 32px; }
.nav-links li { margin-bottom: 4px; }
.nav-links a {
    display: block;
    padding: 10px 14px;
    border-radius: 8px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.9rem;
    transition: background 0.15s, color 0.15s;
}
.nav-links a:hover { background: var(--bg-card); color: var(--text); }
.nav-links a.active { background: var(--accent); color: white; }

/* Main content */
.content {
    margin-left: 220px;
    padding: 32px 40px;
    flex: 1;
    max-width: 1200px;
}

/* Cards */
.card {
    background: var(--bg-card);
    border-radius: var(--radius);
    padding: 24px;
    margin-bottom: 20px;
    border: 1px solid var(--border);
}

.card h3 {
    font-size: 1rem;
    color: var(--text-muted);
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 500;
}

/* Hero stat cards */
.hero-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
}

.hero-card {
    background: var(--bg-card);
    border-radius: var(--radius);
    padding: 24px;
    text-align: center;
    border: 1px solid var(--border);
}

.hero-value {
    font-size: 2.4rem;
    font-weight: 700;
    color: var(--accent-light);
    line-height: 1.1;
}

.hero-label {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-top: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.hero-sub {
    font-size: 0.8rem;
    color: var(--text-dim);
    margin-top: 4px;
}

/* Chapter sections (story) */
.chapter {
    margin-bottom: 48px;
    padding-bottom: 32px;
    border-bottom: 1px solid var(--border);
}

.chapter-number {
    font-size: 0.75rem;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 8px;
}

.chapter h2 {
    font-size: 1.8rem;
    font-weight: 700;
    margin-bottom: 20px;
}

/* Stat rows */
.stat-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
}

.stat-row:last-child { border-bottom: none; }
.stat-row .label { color: var(--text-muted); }
.stat-row .value { font-weight: 600; }

/* Charts */
.chart-container {
    position: relative;
    width: 100%;
    max-height: 300px;
    margin: 16px 0;
}

/* Heatmap grid */
.heatmap {
    display: grid;
    gap: 2px;
    margin: 16px 0;
}

.heatmap-cell {
    aspect-ratio: 1;
    border-radius: 3px;
    min-width: 16px;
    min-height: 16px;
}

/* Chat */
.chat-container { display: flex; flex-direction: column; height: calc(100vh - 100px); }
.chat-log { flex: 1; overflow-y: auto; padding: 16px; }
.chat-input-bar { padding: 16px; border-top: 1px solid var(--border); }
.chat-input-bar input {
    width: 100%;
    padding: 12px 16px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 0.95rem;
}
.chat-message { margin-bottom: 16px; }
.chat-message .sender { font-weight: 600; margin-bottom: 4px; }
.chat-message .body { color: var(--text-muted); }

/* Responsive */
@media (max-width: 768px) {
    .sidebar { display: none; }
    .content { margin-left: 0; padding: 16px; }
    .hero-grid { grid-template-columns: repeat(2, 1fr); }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/slackwrap/web/templates/base.html src/slackwrap/web/static/style.css
git commit -m "feat(v2): add base HTML template with dark theme, sidebar nav, Chart.js CDN"
```

---

### Task 3: JSON API Endpoints

**Files:**
- Modify: `src/slackwrap/web/routes/api.py`
- Create: `tests/test_web_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_web_api.py
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from slackwrap.db import Database
from slackwrap.web.app import create_app


@pytest.fixture
def web_client(db):
    """FastAPI test client with seeded data."""
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()

    for i in range(10):
        ts = 1700049600.0 + i * 86400
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"msg {i} hello world :rocket:", created_at=ts)
    db.commit()

    app = create_app(db=db, you_id=u1, them_id=u2, your_name="Alice", their_name="Bob")
    return TestClient(app)


def test_api_volume(web_client):
    resp = web_client.get("/api/volume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_messages"] == 10
    assert data["you_count"] == 5


def test_api_heatmap(web_client):
    resp = web_client.get("/api/heatmap")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "x_labels" in data


def test_api_trends(web_client):
    resp = web_client.get("/api/trends")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_month" in data


def test_api_streaks(web_client):
    resp = web_client.get("/api/streaks")
    assert resp.status_code == 200
    data = resp.json()
    assert "longest_streak_days" in data


def test_api_communication(web_client):
    resp = web_client.get("/api/communication")
    assert resp.status_code == 200
    data = resp.json()
    assert "your_avg_words" in data


def test_api_response_times(web_client):
    resp = web_client.get("/api/response-times")
    assert resp.status_code == 200
    data = resp.json()
    assert "your_median" in data


def test_api_relationship(web_client):
    resp = web_client.get("/api/relationship")
    assert resp.status_code == 200
    data = resp.json()
    assert "reciprocity_index" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_web_api.py -v`
Expected: FAIL — endpoints return wrong data (stub responses)

- [ ] **Step 3: Implement API endpoints**

```python
# src/slackwrap/web/routes/api.py
from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, Request
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters

router = APIRouter()


def _engine(request: Request) -> AnalyticsEngine:
    return AnalyticsEngine(request.app.state.db)


def _ids(request: Request) -> tuple[int, int]:
    return request.app.state.you_id, request.app.state.them_id


@router.get("/health")
def api_health():
    return {"status": "ok"}


@router.get("/volume")
def api_volume(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    stats = engine.volume(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(stats)


@router.get("/huddles")
def api_huddles(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    stats = engine.huddles(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(stats)


@router.get("/response-times")
def api_response_times(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    stats = engine.response_times(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(stats)


@router.get("/threads")
def api_threads(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    stats = engine.threads(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(stats)


@router.get("/communication")
def api_communication(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    stats = engine.communication(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(stats)


@router.get("/streaks")
def api_streaks(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    stats = engine.streaks(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(stats)


@router.get("/trends")
def api_trends(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    stats = engine.trends(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(stats)


@router.get("/heatmap")
def api_heatmap(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    result = engine.heatmap(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(result)


@router.get("/relationship")
def api_relationship(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    stats = engine.relationship(you_id=you_id, them_id=them_id, filters=Filters())
    return asdict(stats)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_web_api.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/web/routes/api.py tests/test_web_api.py
git commit -m "feat(v2): add JSON API endpoints for all analytics — volume, heatmap, trends, streaks, etc."
```

---

### Task 4: Story Page (Wrapped Narrative)

**Files:**
- Create: `src/slackwrap/web/templates/story.html`
- Modify: `src/slackwrap/web/routes/story.py`
- Create: `tests/test_web_story.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_web_story.py
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from slackwrap.db import Database
from slackwrap.web.app import create_app


@pytest.fixture
def story_client(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(10):
        ts = 1700049600.0 + i * 86400
        user = u1 if i % 2 == 0 else u2
        db.upsert_message(channel_id=ch, user_id=user, slack_ts=f"{ts}.001",
                          text=f"msg {i} hello world", created_at=ts)
    db.commit()
    app = create_app(db=db, you_id=u1, them_id=u2, your_name="Alice", their_name="Bob")
    return TestClient(app)


def test_story_page_returns_html(story_client):
    resp = story_client.get("/story")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_story_page_contains_chapters(story_client):
    resp = story_client.get("/story")
    html = resp.text
    assert "Your Year Together" in html
    assert "By the Numbers" in html
    assert "Your Rhythm" in html


def test_story_page_contains_stats(story_client):
    resp = story_client.get("/story")
    html = resp.text
    assert "Alice" in html
    assert "Bob" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_web_story.py -v`
Expected: FAIL

- [ ] **Step 3: Implement story route with template rendering**

```python
# src/slackwrap/web/routes/story.py
from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters

router = APIRouter()


def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes:02d}m" if parts else f"{minutes}m")
    return " ".join(parts) if parts else "0m"


@router.get("", response_class=HTMLResponse)
def story_page(request: Request):
    db = request.app.state.db
    you_id = request.app.state.you_id
    them_id = request.app.state.them_id
    your_name = request.app.state.your_name
    their_name = request.app.state.their_name
    templates = request.app.state.templates

    engine = AnalyticsEngine(db)
    filters = Filters()

    vol = engine.volume(you_id=you_id, them_id=them_id, filters=filters)
    huddle = engine.huddles(you_id=you_id, them_id=them_id, filters=filters)
    resp_time = engine.response_times(you_id=you_id, them_id=them_id, filters=filters)
    streaks = engine.streaks(you_id=you_id, them_id=them_id, filters=filters)
    comm = engine.communication(you_id=you_id, them_id=them_id, filters=filters)
    threads = engine.threads(you_id=you_id, them_id=them_id, filters=filters)
    trends = engine.trends(you_id=you_id, them_id=them_id, filters=filters)
    heatmap = engine.heatmap(you_id=you_id, them_id=them_id, filters=filters)
    rel = engine.relationship(you_id=you_id, them_id=them_id, filters=filters)

    return templates.TemplateResponse("story.html", {
        "request": request,
        "active_page": "story",
        "your_name": your_name,
        "their_name": their_name,
        "vol": asdict(vol),
        "huddle": asdict(huddle),
        "resp_time": asdict(resp_time),
        "streaks": asdict(streaks),
        "comm": asdict(comm),
        "threads": asdict(threads),
        "trends": asdict(trends),
        "heatmap": asdict(heatmap),
        "rel": asdict(rel),
        "format_duration": _format_duration,
    })
```

- [ ] **Step 4: Create story template**

```html
<!-- src/slackwrap/web/templates/story.html -->
{% extends "base.html" %}
{% block title %}SlackWrap — Your Story{% endblock %}
{% block content %}

<!-- Hero -->
<div class="hero-grid">
    <div class="hero-card">
        <div class="hero-value">{{ "{:,}".format(vol.total_messages) }}</div>
        <div class="hero-label">Messages</div>
        <div class="hero-sub">{{ vol.total_days }} days</div>
    </div>
    {% if huddle.total_huddles > 0 %}
    <div class="hero-card">
        <div class="hero-value">{{ huddle.total_huddles }}</div>
        <div class="hero-label">Huddles</div>
        <div class="hero-sub">{{ format_duration(huddle.total_seconds) }}</div>
    </div>
    {% endif %}
    {% if streaks.longest_streak_days > 0 %}
    <div class="hero-card">
        <div class="hero-value">{{ streaks.longest_streak_days }}d</div>
        <div class="hero-label">Best Streak</div>
        <div class="hero-sub">Current: {{ streaks.current_streak_days }}d</div>
    </div>
    {% endif %}
    <div class="hero-card">
        <div class="hero-value">{{ vol.active_days }}</div>
        <div class="hero-label">Active Days</div>
        <div class="hero-sub">of {{ vol.total_days }} total</div>
    </div>
</div>

<!-- Chapter 1: Your Year Together -->
<div class="chapter">
    <div class="chapter-number">Chapter 1</div>
    <h2>Your Year Together</h2>
    <div class="card">
        <div class="stat-row"><span class="label">Period</span><span class="value">{{ vol.total_days }} days</span></div>
        <div class="stat-row"><span class="label">Total messages</span><span class="value">{{ "{:,}".format(vol.total_messages) }}</span></div>
        {% if huddle.total_huddles > 0 %}
        <div class="stat-row"><span class="label">Huddle time</span><span class="value">{{ format_duration(huddle.total_seconds) }}</span></div>
        {% endif %}
        <div class="stat-row"><span class="label">Active days</span><span class="value">{{ vol.active_days }}</span></div>
    </div>
</div>

<!-- Chapter 2: By the Numbers -->
<div class="chapter">
    <div class="chapter-number">Chapter 2</div>
    <h2>By the Numbers</h2>
    <div class="card">
        <h3>Messages</h3>
        <div class="stat-row"><span class="label">{{ your_name }}</span><span class="value">{{ "{:,}".format(vol.you_count) }} ({{ vol.you_pct }}%)</span></div>
        <div class="stat-row"><span class="label">{{ their_name }}</span><span class="value">{{ "{:,}".format(vol.them_count) }} ({{ vol.them_pct }}%)</span></div>
        <div class="stat-row"><span class="label">Per week</span><span class="value">{{ vol.per_week }}</span></div>
        {% if vol.busiest_day_date %}
        <div class="stat-row"><span class="label">Busiest day</span><span class="value">{{ vol.busiest_day_date }} ({{ vol.busiest_day_count }} msgs)</span></div>
        {% endif %}
    </div>
    {% if threads.total_messages > 0 %}
    <div class="card">
        <h3>Threads</h3>
        <div class="stat-row"><span class="label">Top-level</span><span class="value">{{ "{:,}".format(threads.top_level) }}</span></div>
        <div class="stat-row"><span class="label">In threads</span><span class="value">{{ "{:,}".format(threads.in_threads) }} ({{ threads.thread_pct }}%)</span></div>
    </div>
    {% endif %}
    <div class="card">
        <h3>Weekend vs Weekday</h3>
        <div class="stat-row"><span class="label">Weekday</span><span class="value">{{ "{:,}".format(vol.weekday_count) }}</span></div>
        <div class="stat-row"><span class="label">Weekend</span><span class="value">{{ "{:,}".format(vol.weekend_count) }}</span></div>
    </div>
</div>

<!-- Chapter 3: Your Rhythm -->
<div class="chapter">
    <div class="chapter-number">Chapter 3</div>
    <h2>Your Rhythm</h2>
    <div class="card">
        <h3>Activity Heatmap</h3>
        <div class="chart-container">
            <canvas id="heatmap-chart"></canvas>
        </div>
    </div>
    {% if resp_time.your_median > 0 or resp_time.their_median > 0 %}
    <div class="card">
        <h3>Response Time</h3>
        <div class="stat-row"><span class="label">{{ your_name }}</span><span class="value">{{ format_duration(resp_time.your_median) }} median</span></div>
        <div class="stat-row"><span class="label">{{ their_name }}</span><span class="value">{{ format_duration(resp_time.their_median) }} median</span></div>
    </div>
    {% endif %}
</div>

<!-- Chapter 4: How You Communicate -->
<div class="chapter">
    <div class="chapter-number">Chapter 4</div>
    <h2>How You Communicate</h2>
    <div class="card">
        <h3>Message Style</h3>
        <div class="stat-row"><span class="label">{{ your_name }} avg words</span><span class="value">{{ comm.your_avg_words }}</span></div>
        <div class="stat-row"><span class="label">{{ their_name }} avg words</span><span class="value">{{ comm.their_avg_words }}</span></div>
    </div>
    {% if comm.your_top_words or comm.their_top_words %}
    <div class="card">
        <h3>Most Used Words</h3>
        {% if comm.your_top_words %}
        <div class="stat-row"><span class="label">{{ your_name }}</span><span class="value">{{ comm.your_top_words[:5] | map(attribute=0) | join(', ') }}</span></div>
        {% endif %}
        {% if comm.their_top_words %}
        <div class="stat-row"><span class="label">{{ their_name }}</span><span class="value">{{ comm.their_top_words[:5] | map(attribute=0) | join(', ') }}</span></div>
        {% endif %}
    </div>
    {% endif %}
    {% if comm.your_emoji_total > 0 or comm.their_emoji_total > 0 %}
    <div class="card">
        <h3>Emoji Usage</h3>
        <div class="stat-row"><span class="label">{{ your_name }}</span><span class="value">{{ comm.your_emoji_total }} emojis ({{ comm.emoji_diversity_you }} unique)</span></div>
        <div class="stat-row"><span class="label">{{ their_name }}</span><span class="value">{{ comm.their_emoji_total }} emojis ({{ comm.emoji_diversity_them }} unique)</span></div>
    </div>
    {% endif %}
</div>

<!-- Chapter 5: Highlights -->
<div class="chapter">
    <div class="chapter-number">Chapter 5</div>
    <h2>Highlights</h2>
    {% if rel.first_message %}
    <div class="card">
        <h3>First &amp; Last</h3>
        <div class="stat-row"><span class="label">First message</span><span class="value">"{{ rel.first_message.text[:80] }}"</span></div>
        <div class="stat-row"><span class="label">Last message</span><span class="value">"{{ rel.last_message.text[:80] }}"</span></div>
    </div>
    {% endif %}
    {% if rel.pinned_highlights %}
    <div class="card">
        <h3>Pinned Messages</h3>
        <p style="color: var(--text-muted);">{{ rel.pinned_highlights | length }} pinned messages</p>
    </div>
    {% endif %}
</div>

<!-- Chapter 6: Your Streaks -->
<div class="chapter">
    <div class="chapter-number">Chapter 6</div>
    <h2>Your Streaks</h2>
    <div class="card">
        <div class="stat-row"><span class="label">Longest streak</span><span class="value">{{ streaks.longest_streak_days }} days</span></div>
        <div class="stat-row"><span class="label">Current streak</span><span class="value">{{ streaks.current_streak_days }} days</span></div>
        {% if streaks.longest_gap_seconds > 0 %}
        <div class="stat-row"><span class="label">Longest silence</span><span class="value">{{ (streaks.longest_gap_seconds // 86400) }} days</span></div>
        {% endif %}
    </div>
    {% if streaks.milestones %}
    <div class="card">
        <h3>Milestones</h3>
        {% for label, date in streaks.milestones.items() %}
        <div class="stat-row"><span class="label">{{ label }}</span><span class="value">{{ date }}</span></div>
        {% endfor %}
    </div>
    {% endif %}
</div>

<!-- Chapter 7: Trends -->
<div class="chapter">
    <div class="chapter-number">Chapter 7</div>
    <h2>Trends</h2>
    <div class="card">
        <h3>Monthly Volume</h3>
        <div class="chart-container">
            <canvas id="monthly-chart"></canvas>
        </div>
    </div>
    <div class="card">
        <div class="stat-row"><span class="label">Last 30 days</span><span class="value">{{ trends.last_30d_count }} msgs{% if trends.pct_change_30d is not none %} ({{ "+" if trends.pct_change_30d >= 0 }}{{ trends.pct_change_30d }}%){% endif %}</span></div>
    </div>
</div>

<!-- Charts JS -->
<script>
// Monthly volume chart
const monthlyCtx = document.getElementById('monthly-chart');
if (monthlyCtx) {
    const monthlyData = {{ vol.monthly_volumes | tojson }};
    new Chart(monthlyCtx, {
        type: 'bar',
        data: {
            labels: Object.keys(monthlyData),
            datasets: [{
                label: 'Messages',
                data: Object.values(monthlyData),
                backgroundColor: 'rgba(108, 92, 231, 0.6)',
                borderColor: 'rgba(108, 92, 231, 1)',
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b8b9e' } },
                x: { grid: { display: false }, ticks: { color: '#8b8b9e' } }
            }
        }
    });
}

// Heatmap as a bar chart (grouped by day of week)
const heatmapCtx = document.getElementById('heatmap-chart');
if (heatmapCtx) {
    const heatmapData = {{ heatmap.data | tojson }};
    const dayLabels = {{ heatmap.x_labels | tojson }};

    // Sum counts per day of week
    const dayCounts = dayLabels.map((_, i) => {
        const hourData = heatmapData[String(i)] || {};
        return Object.values(hourData).reduce((a, b) => a + b, 0);
    });

    new Chart(heatmapCtx, {
        type: 'bar',
        data: {
            labels: dayLabels,
            datasets: [{
                label: 'Messages',
                data: dayCounts,
                backgroundColor: 'rgba(0, 184, 148, 0.6)',
                borderColor: 'rgba(0, 184, 148, 1)',
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b8b9e' } },
                x: { grid: { display: false }, ticks: { color: '#8b8b9e' } }
            }
        }
    });
}
</script>

{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_web_story.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/slackwrap/web/routes/story.py src/slackwrap/web/templates/story.html tests/test_web_story.py
git commit -m "feat(v2): add Wrapped story page — 7 chapters with Chart.js charts, dark theme"
```

---

### Task 5: Explore Page

**Files:**
- Create: `src/slackwrap/web/templates/explore.html`
- Modify: `src/slackwrap/web/routes/explore.py`
- Create: `tests/test_web_explore.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_web_explore.py
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from slackwrap.web.app import create_app


@pytest.fixture
def explore_client(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(5):
        ts = 1700049600.0 + i * 86400
        db.upsert_message(channel_id=ch, user_id=u1 if i % 2 == 0 else u2,
                          slack_ts=f"{ts}.001", text=f"msg {i}", created_at=ts)
    db.commit()
    app = create_app(db=db, you_id=u1, them_id=u2, your_name="Alice", their_name="Bob")
    return TestClient(app)


def test_explore_page_returns_html(explore_client):
    resp = explore_client.get("/explore")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_explore_page_has_charts(explore_client):
    resp = explore_client.get("/explore")
    assert "chart" in resp.text.lower() or "Chart" in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_web_explore.py -v`
Expected: FAIL

- [ ] **Step 3: Implement explore route**

```python
# src/slackwrap/web/routes/explore.py
from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters

router = APIRouter()


@router.get("", response_class=HTMLResponse)
def explore_page(request: Request):
    db = request.app.state.db
    you_id = request.app.state.you_id
    them_id = request.app.state.them_id
    templates = request.app.state.templates

    engine = AnalyticsEngine(db)
    filters = Filters()

    vol = engine.volume(you_id=you_id, them_id=them_id, filters=filters)
    heatmap = engine.heatmap(you_id=you_id, them_id=them_id, filters=filters)
    resp_time = engine.response_times(you_id=you_id, them_id=them_id, filters=filters)
    comm = engine.communication(you_id=you_id, them_id=them_id, filters=filters)

    return templates.TemplateResponse("explore.html", {
        "request": request,
        "active_page": "explore",
        "your_name": request.app.state.your_name,
        "their_name": request.app.state.their_name,
        "vol": asdict(vol),
        "heatmap": asdict(heatmap),
        "resp_time": asdict(resp_time),
        "comm": asdict(comm),
    })
```

- [ ] **Step 4: Create explore template**

```html
<!-- src/slackwrap/web/templates/explore.html -->
{% extends "base.html" %}
{% block title %}SlackWrap — Explore{% endblock %}
{% block content %}

<h1 style="margin-bottom: 24px;">Explore</h1>

<div class="hero-grid">
    <div class="hero-card">
        <div class="hero-value">{{ "{:,}".format(vol.total_messages) }}</div>
        <div class="hero-label">Messages</div>
    </div>
    <div class="hero-card">
        <div class="hero-value">{{ vol.active_days }}</div>
        <div class="hero-label">Active Days</div>
    </div>
    <div class="hero-card">
        <div class="hero-value">{{ vol.per_week }}</div>
        <div class="hero-label">Per Week</div>
    </div>
    <div class="hero-card">
        <div class="hero-value">{{ vol.messages_per_active_day }}</div>
        <div class="hero-label">Per Active Day</div>
    </div>
</div>

<div class="card">
    <h3>Monthly Volume</h3>
    <div class="chart-container"><canvas id="explore-monthly"></canvas></div>
</div>

<div class="card">
    <h3>Activity by Day of Week</h3>
    <div class="chart-container"><canvas id="explore-dow"></canvas></div>
</div>

<div class="card">
    <h3>Message Split</h3>
    <div class="chart-container" style="max-width: 300px; margin: 0 auto;">
        <canvas id="explore-split"></canvas>
    </div>
</div>

{% if resp_time.monthly_trend %}
<div class="card">
    <h3>Response Time Trend</h3>
    <div class="chart-container"><canvas id="explore-resp-trend"></canvas></div>
</div>
{% endif %}

<script>
// Monthly volume
const monthlyData = {{ vol.monthly_volumes | tojson }};
new Chart(document.getElementById('explore-monthly'), {
    type: 'bar',
    data: {
        labels: Object.keys(monthlyData),
        datasets: [{
            label: 'Messages', data: Object.values(monthlyData),
            backgroundColor: 'rgba(108, 92, 231, 0.6)', borderRadius: 4,
        }]
    },
    options: {
        responsive: true, plugins: { legend: { display: false } },
        scales: {
            y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b8b9e' } },
            x: { grid: { display: false }, ticks: { color: '#8b8b9e' } }
        }
    }
});

// Day of week
const heatmapData = {{ heatmap.data | tojson }};
const dayLabels = {{ heatmap.x_labels | tojson }};
const dayCounts = dayLabels.map((_, i) => {
    const hd = heatmapData[String(i)] || {};
    return Object.values(hd).reduce((a, b) => a + b, 0);
});
new Chart(document.getElementById('explore-dow'), {
    type: 'bar',
    data: {
        labels: dayLabels,
        datasets: [{
            label: 'Messages', data: dayCounts,
            backgroundColor: 'rgba(0, 184, 148, 0.6)', borderRadius: 4,
        }]
    },
    options: {
        responsive: true, plugins: { legend: { display: false } },
        scales: {
            y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b8b9e' } },
            x: { grid: { display: false }, ticks: { color: '#8b8b9e' } }
        }
    }
});

// Message split doughnut
new Chart(document.getElementById('explore-split'), {
    type: 'doughnut',
    data: {
        labels: ['{{ your_name }}', '{{ their_name }}'],
        datasets: [{
            data: [{{ vol.you_count }}, {{ vol.them_count }}],
            backgroundColor: ['rgba(108, 92, 231, 0.8)', 'rgba(0, 184, 148, 0.8)'],
        }]
    },
    options: { responsive: true, plugins: { legend: { labels: { color: '#8b8b9e' } } } }
});

// Response time trend
{% if resp_time.monthly_trend %}
const rtData = {{ resp_time.monthly_trend | tojson }};
new Chart(document.getElementById('explore-resp-trend'), {
    type: 'line',
    data: {
        labels: Object.keys(rtData),
        datasets: [{
            label: 'Median Response (s)', data: Object.values(rtData),
            borderColor: 'rgba(253, 203, 110, 1)', tension: 0.3, fill: false,
        }]
    },
    options: {
        responsive: true, plugins: { legend: { display: false } },
        scales: {
            y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b8b9e' } },
            x: { grid: { display: false }, ticks: { color: '#8b8b9e' } }
        }
    }
});
{% endif %}
</script>

{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_web_explore.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/slackwrap/web/routes/explore.py src/slackwrap/web/templates/explore.html tests/test_web_explore.py
git commit -m "feat(v2): add Explore page — interactive charts for volume, heatmap, split, response trends"
```

---

### Task 6: Deep Dives Pages

**Files:**
- Create: `src/slackwrap/web/templates/deep_dives/index.html`
- Create: `src/slackwrap/web/templates/deep_dives/response_time.html`
- Create: `src/slackwrap/web/templates/deep_dives/communication.html`
- Create: `src/slackwrap/web/templates/deep_dives/activity.html`
- Modify: `src/slackwrap/web/routes/deep_dives.py`
- Create: `tests/test_web_deep_dives.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_web_deep_dives.py
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from slackwrap.web.app import create_app


@pytest.fixture
def dd_client(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    for i in range(5):
        ts = 1700049600.0 + i * 86400
        db.upsert_message(channel_id=ch, user_id=u1 if i % 2 == 0 else u2,
                          slack_ts=f"{ts}.001", text=f"msg {i} hello :rocket:", created_at=ts)
    db.commit()
    app = create_app(db=db, you_id=u1, them_id=u2, your_name="Alice", their_name="Bob")
    return TestClient(app)


def test_deep_dives_index(dd_client):
    resp = dd_client.get("/deep-dives")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Response Time" in resp.text


def test_deep_dives_response_time(dd_client):
    resp = dd_client.get("/deep-dives/response-time")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_deep_dives_communication(dd_client):
    resp = dd_client.get("/deep-dives/communication")
    assert resp.status_code == 200


def test_deep_dives_activity(dd_client):
    resp = dd_client.get("/deep-dives/activity")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_web_deep_dives.py -v`
Expected: FAIL

- [ ] **Step 3: Implement deep dives routes**

```python
# src/slackwrap/web/routes/deep_dives.py
from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters

router = APIRouter()


def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes:02d}m" if parts else f"{minutes}m")
    return " ".join(parts) if parts else "0m"


def _ctx(request: Request) -> dict:
    db = request.app.state.db
    you_id = request.app.state.you_id
    them_id = request.app.state.them_id
    return {
        "request": request,
        "active_page": "deep-dives",
        "your_name": request.app.state.your_name,
        "their_name": request.app.state.their_name,
        "db": db, "you_id": you_id, "them_id": them_id,
        "templates": request.app.state.templates,
        "format_duration": _format_duration,
    }


@router.get("", response_class=HTMLResponse)
def deep_dives_index(request: Request):
    ctx = _ctx(request)
    return ctx["templates"].TemplateResponse("deep_dives/index.html", {
        "request": request, "active_page": "deep-dives",
        "your_name": ctx["your_name"], "their_name": ctx["their_name"],
    })


@router.get("/response-time", response_class=HTMLResponse)
def response_time_page(request: Request):
    ctx = _ctx(request)
    engine = AnalyticsEngine(ctx["db"])
    resp_time = engine.response_times(you_id=ctx["you_id"], them_id=ctx["them_id"], filters=Filters())
    return ctx["templates"].TemplateResponse("deep_dives/response_time.html", {
        "request": request, "active_page": "deep-dives",
        "your_name": ctx["your_name"], "their_name": ctx["their_name"],
        "resp_time": asdict(resp_time),
        "format_duration": _format_duration,
    })


@router.get("/communication", response_class=HTMLResponse)
def communication_page(request: Request):
    ctx = _ctx(request)
    engine = AnalyticsEngine(ctx["db"])
    comm = engine.communication(you_id=ctx["you_id"], them_id=ctx["them_id"], filters=Filters())
    return ctx["templates"].TemplateResponse("deep_dives/communication.html", {
        "request": request, "active_page": "deep-dives",
        "your_name": ctx["your_name"], "their_name": ctx["their_name"],
        "comm": asdict(comm),
    })


@router.get("/activity", response_class=HTMLResponse)
def activity_page(request: Request):
    ctx = _ctx(request)
    engine = AnalyticsEngine(ctx["db"])
    vol = engine.volume(you_id=ctx["you_id"], them_id=ctx["them_id"], filters=Filters())
    heatmap = engine.heatmap(you_id=ctx["you_id"], them_id=ctx["them_id"], filters=Filters())
    return ctx["templates"].TemplateResponse("deep_dives/activity.html", {
        "request": request, "active_page": "deep-dives",
        "your_name": ctx["your_name"], "their_name": ctx["their_name"],
        "vol": asdict(vol), "heatmap": asdict(heatmap),
    })
```

- [ ] **Step 4: Create deep dive templates**

```html
<!-- src/slackwrap/web/templates/deep_dives/index.html -->
{% extends "base.html" %}
{% block title %}SlackWrap — Deep Dives{% endblock %}
{% block content %}
<h1 style="margin-bottom: 24px;">Deep Dives</h1>
<div class="hero-grid">
    <a href="/deep-dives/response-time" class="hero-card" style="text-decoration:none; color:inherit;">
        <div class="hero-label">Response Time</div>
        <div class="hero-sub">Trends, by hour, comparison</div>
    </a>
    <a href="/deep-dives/communication" class="hero-card" style="text-decoration:none; color:inherit;">
        <div class="hero-label">Communication Style</div>
        <div class="hero-sub">Words, emoji, reactions</div>
    </a>
    <a href="/deep-dives/activity" class="hero-card" style="text-decoration:none; color:inherit;">
        <div class="hero-label">Activity Patterns</div>
        <div class="hero-sub">Heatmaps, peak hours</div>
    </a>
</div>
{% endblock %}
```

```html
<!-- src/slackwrap/web/templates/deep_dives/response_time.html -->
{% extends "base.html" %}
{% block title %}SlackWrap — Response Time{% endblock %}
{% block content %}
<h1 style="margin-bottom: 24px;">Response Time Analysis</h1>
<div class="card">
    <h3>Overview</h3>
    <div class="stat-row"><span class="label">{{ your_name }} median</span><span class="value">{{ format_duration(resp_time.your_median) }}</span></div>
    <div class="stat-row"><span class="label">{{ their_name }} median</span><span class="value">{{ format_duration(resp_time.their_median) }}</span></div>
    <div class="stat-row"><span class="label">{{ your_name }} avg</span><span class="value">{{ format_duration(resp_time.your_avg) }}</span></div>
    <div class="stat-row"><span class="label">{{ their_name }} avg</span><span class="value">{{ format_duration(resp_time.their_avg) }}</span></div>
</div>
{% if resp_time.by_hour %}
<div class="card">
    <h3>By Hour of Day</h3>
    <div class="chart-container"><canvas id="resp-hour"></canvas></div>
</div>
<script>
const byHour = {{ resp_time.by_hour | tojson }};
const hours = Object.keys(byHour).map(h => h + ':00');
const times = Object.values(byHour);
new Chart(document.getElementById('resp-hour'), {
    type: 'bar', data: { labels: hours, datasets: [{ label: 'Median (s)', data: times, backgroundColor: 'rgba(253, 203, 110, 0.6)', borderRadius: 4 }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b8b9e' } }, x: { grid: { display: false }, ticks: { color: '#8b8b9e' } } } }
});
</script>
{% endif %}
{% endblock %}
```

```html
<!-- src/slackwrap/web/templates/deep_dives/communication.html -->
{% extends "base.html" %}
{% block title %}SlackWrap — Communication Style{% endblock %}
{% block content %}
<h1 style="margin-bottom: 24px;">Communication Style</h1>
<div class="card">
    <h3>Word Count</h3>
    <div class="stat-row"><span class="label">{{ your_name }} avg</span><span class="value">{{ comm.your_avg_words }} words</span></div>
    <div class="stat-row"><span class="label">{{ their_name }} avg</span><span class="value">{{ comm.their_avg_words }} words</span></div>
</div>
{% if comm.message_length_distribution %}
<div class="card">
    <h3>Message Length Distribution</h3>
    <div class="chart-container"><canvas id="length-dist"></canvas></div>
</div>
<script>
const dist = {{ comm.message_length_distribution | tojson }};
new Chart(document.getElementById('length-dist'), {
    type: 'doughnut', data: { labels: Object.keys(dist), datasets: [{ data: Object.values(dist), backgroundColor: ['rgba(108,92,231,0.8)', 'rgba(0,184,148,0.8)', 'rgba(253,203,110,0.8)'] }] },
    options: { responsive: true, plugins: { legend: { labels: { color: '#8b8b9e' } } } }
});
</script>
{% endif %}
<div class="card">
    <h3>Emoji Usage</h3>
    <div class="stat-row"><span class="label">{{ your_name }}</span><span class="value">{{ comm.your_emoji_total }} ({{ comm.emoji_diversity_you }} unique)</span></div>
    <div class="stat-row"><span class="label">{{ their_name }}</span><span class="value">{{ comm.their_emoji_total }} ({{ comm.emoji_diversity_them }} unique)</span></div>
</div>
<div class="card">
    <h3>Reactions</h3>
    <div class="stat-row"><span class="label">{{ your_name }} given</span><span class="value">{{ comm.your_reactions_given }}</span></div>
    <div class="stat-row"><span class="label">{{ their_name }} given</span><span class="value">{{ comm.their_reactions_given }}</span></div>
</div>
{% endblock %}
```

```html
<!-- src/slackwrap/web/templates/deep_dives/activity.html -->
{% extends "base.html" %}
{% block title %}SlackWrap — Activity Patterns{% endblock %}
{% block content %}
<h1 style="margin-bottom: 24px;">Activity Patterns</h1>
<div class="card">
    <h3>Day of Week</h3>
    <div class="chart-container"><canvas id="act-dow"></canvas></div>
</div>
<div class="card">
    <h3>Weekend vs Weekday</h3>
    <div class="stat-row"><span class="label">Weekday</span><span class="value">{{ "{:,}".format(vol.weekday_count) }}</span></div>
    <div class="stat-row"><span class="label">Weekend</span><span class="value">{{ "{:,}".format(vol.weekend_count) }}</span></div>
    <div class="stat-row"><span class="label">Messages per active day</span><span class="value">{{ vol.messages_per_active_day }}</span></div>
</div>
{% if vol.monthly_rank %}
<div class="card">
    <h3>Monthly Rank</h3>
    {% for month, count, rank in vol.monthly_rank[:6] %}
    <div class="stat-row"><span class="label">#{{ rank }} {{ month }}</span><span class="value">{{ "{:,}".format(count) }} msgs</span></div>
    {% endfor %}
</div>
{% endif %}
<script>
const heatmapData = {{ heatmap.data | tojson }};
const dayLabels = {{ heatmap.x_labels | tojson }};
const dayCounts = dayLabels.map((_, i) => {
    const hd = heatmapData[String(i)] || {};
    return Object.values(hd).reduce((a, b) => a + b, 0);
});
new Chart(document.getElementById('act-dow'), {
    type: 'bar', data: { labels: dayLabels, datasets: [{ label: 'Messages', data: dayCounts, backgroundColor: 'rgba(0,184,148,0.6)', borderRadius: 4 }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b8b9e' } }, x: { grid: { display: false }, ticks: { color: '#8b8b9e' } } } }
});
</script>
{% endblock %}
```

- [ ] **Step 5: Create the templates directory for deep dives**

Run: `mkdir -p src/slackwrap/web/templates/deep_dives`

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_web_deep_dives.py -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/slackwrap/web/routes/deep_dives.py src/slackwrap/web/templates/deep_dives/ tests/test_web_deep_dives.py
git commit -m "feat(v2): add Deep Dives pages — response time, communication, activity with charts"
```

---

### Task 7: Chat Page Stub + Wire Up TUI

**Files:**
- Create: `src/slackwrap/web/templates/chat.html`
- Modify: `src/slackwrap/web/routes/chat.py`
- Modify: `src/slackwrap/tui/app.py` — wire `action_open_web` to launch WebServer
- Modify: `src/slackwrap/tui/screens/dashboard.py` — wire `action_open_web`

- [ ] **Step 1: Create chat template**

```html
<!-- src/slackwrap/web/templates/chat.html -->
{% extends "base.html" %}
{% block title %}SlackWrap — Chat{% endblock %}
{% block content %}
<div class="chat-container">
    <h1 style="margin-bottom: 16px;">Chat with your data</h1>
    <div class="chat-log" id="chat-log">
        <div class="chat-message">
            <div class="sender" style="color: var(--accent-light);">SlackWrap</div>
            <div class="body">Chat requires Ollama to be running locally. This feature will be available in Plan 5 (AI Layer).</div>
        </div>
        <div class="chat-message">
            <div class="sender" style="color: var(--accent-light);">SlackWrap</div>
            <div class="body">Install Ollama: <a href="https://ollama.ai" style="color: var(--accent-light);">ollama.ai</a> | Start: <code>ollama serve</code></div>
        </div>
    </div>
    <div class="chat-input-bar">
        <input type="text" id="chat-input" placeholder="Ask anything about your Slack history..." disabled>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Update chat route**

```python
# src/slackwrap/web/routes/chat.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("", response_class=HTMLResponse)
def chat_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "active_page": "chat",
        "your_name": request.app.state.your_name,
        "their_name": request.app.state.their_name,
    })
```

- [ ] **Step 3: Wire TUI app to launch web server**

Update `src/slackwrap/tui/app.py` — replace `action_open_web`:

```python
    def action_open_web(self) -> None:
        if not self.you_db_id or not self.them_db_id:
            self.notify("No data loaded. Sync first.")
            return
        if not hasattr(self, '_web_server') or self._web_server is None:
            from slackwrap.web.server import WebServer
            self._web_server = WebServer(
                db=self.db,
                you_id=self.you_db_id,
                them_id=self.them_db_id,
                your_name="You",
                their_name=self.selected_user_name or "Them",
            )
            self._web_server.start()
        import webbrowser
        webbrowser.open(f"{self._web_server.url}/story")
        self.notify(f"Web view: {self._web_server.url}")
```

Update `src/slackwrap/tui/screens/dashboard.py` — replace `action_open_web`:

```python
    def action_open_web(self) -> None:
        self.app.action_open_web()
```

- [ ] **Step 4: Run all web tests**

Run: `python3 -m pytest tests/test_web_*.py -v`
Expected: All web tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/slackwrap/web/routes/chat.py src/slackwrap/web/templates/chat.html src/slackwrap/tui/app.py src/slackwrap/tui/screens/dashboard.py
git commit -m "feat(v2): add Chat stub, wire TUI to launch web server on 'w' keybind"
```

---

### Task 8: Update Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add FastAPI and uvicorn dependencies**

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
dev = [
    "pytest>=8.0.0",
    "httpx>=0.24.0",
]

[project.scripts]
slackwrap = "slackwrap.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest tests/test_web_*.py tests/test_tui_*.py tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(v2): add fastapi, uvicorn, jinja2 dependencies for web view"
```

---

## Plan Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | WebServer — uvicorn in background thread, FastAPI app factory, route stubs | 3 |
| 2 | Base template + dark theme CSS + Chart.js CDN | 0 |
| 3 | JSON API endpoints — all analytics as REST | 7 |
| 4 | Story page — Wrapped narrative with 7 chapters + charts | 3 |
| 5 | Explore page — interactive dashboard with 4 charts | 2 |
| 6 | Deep Dives — 3 analytical pages (response time, communication, activity) | 4 |
| 7 | Chat stub + wire TUI `w` keybind to launch web server | 0 |
| 8 | Dependencies — fastapi, uvicorn, jinja2, httpx | 0 |

**Total: 8 tasks, 19 tests, ~8 commits**

After this plan, pressing `w` in the TUI opens a polished web dashboard with the full Wrapped story, interactive explorer, deep dive analytics, and a chat placeholder. Plan 5 (AI Layer) will wire up the chat for both TUI and web.
