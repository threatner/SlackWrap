# Contributing to SlackWrap

## Setup

1. Clone the repo
2. Create a virtual environment: `python -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install -e ".[dev]"`
4. Copy config: `cp .env.example .env` and add your Slack token

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

- `src/` — source code
  - `main.py` — CLI entry point and interactive menu
  - `slack_client.py` — Slack API wrapper with thread-safe rate limiting
  - `cache.py` — persistent JSON message cache with versioning
  - `engine/` — pure computation (no I/O)
    - `models.py` — data models (User, Conversation, WorkspaceStats, etc.)
    - `conversation_stats.py` — per-conversation stats computation
    - `mentions.py` — mention extraction and counting
    - `workspace_stats.py` — workspace-level aggregation
  - `orchestrators/` — flow controllers
    - `person_flow.py` — one-on-one report flow
    - `workspace_flow.py` — workspace fetch pipeline and wrap orchestrator
  - `reports/` — output formatters for workspace wrap
    - `workspace_console.py` — plain-text workspace report
    - `workspace_html.py` — workspace HTML dashboard
  - `report.py` — huddle stats and console formatter (one-on-one)
  - `message_analytics.py` — message stats and console formatter (one-on-one)
  - `combined_report.py` — unified huddle + message console report (one-on-one)
  - `html_report.py` — HTML dashboard generator (one-on-one)
- `tests/` — test suite

## Guidelines

- Follow existing code style
- Add tests for new features
- Run the full test suite before submitting PRs
- Keep commits focused and descriptive

## Privacy

This tool caches Slack message data locally in `.cache/`. Never commit cache files or `.env` to the repository.
