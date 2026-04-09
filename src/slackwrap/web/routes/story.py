from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters

router = APIRouter()


def format_duration(seconds: int | float) -> str:
    """Human-readable duration from seconds."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "0m"


@router.get("/story", response_class=HTMLResponse)
async def story_page(request: Request):
    db = request.app.state.db
    you_id = request.app.state.you_id
    them_id = request.app.state.them_id
    your_name = request.app.state.your_name
    their_name = request.app.state.their_name
    templates = request.app.state.templates

    engine = AnalyticsEngine(db)
    f = Filters()

    volume = asdict(engine.volume(you_id, them_id, f))
    huddles = asdict(engine.huddles(you_id, them_id, f))
    response_times = asdict(engine.response_times(you_id, them_id, f))
    streaks = asdict(engine.streaks(you_id, them_id, f))
    comm = asdict(engine.communication(you_id, them_id, f))
    threads = asdict(engine.threads(you_id, them_id, f))
    trends = asdict(engine.trends(you_id, them_id, f))
    heatmap = asdict(engine.heatmap(you_id, them_id, f))
    relationship = asdict(engine.relationship(you_id, them_id, f))

    return templates.TemplateResponse(
        "story.html",
        {
            "request": request,
            "active_page": "story",
            "your_name": your_name,
            "their_name": their_name,
            "volume": volume,
            "huddles": huddles,
            "response_times": response_times,
            "streaks": streaks,
            "comm": comm,
            "threads": threads,
            "trends": trends,
            "heatmap": heatmap,
            "relationship": relationship,
            "format_duration": format_duration,
        },
    )
