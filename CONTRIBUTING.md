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
  - `main.py` — CLI entry point and interactive flow
  - `slack_client.py` — Slack API wrapper with rate limiting
  - `message_analytics.py` — message stats computation and formatting
  - `report.py` — huddle stats, shared utilities (format_duration, median, etc.)
  - `combined_report.py` — unified huddle + message console report
  - `html_report.py` — HTML dashboard generator with Chart.js
  - `cache.py` — persistent JSON message cache
- `tests/` — test suite

## Guidelines

- Follow existing code style
- Add tests for new features
- Run the full test suite before submitting PRs
- Keep commits focused and descriptive

## Privacy

This tool caches Slack message data locally in `.cache/`. Never commit cache files or `.env` to the repository.
