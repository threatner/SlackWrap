from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters

router = APIRouter()


def _format_duration(seconds: int | float) -> str:
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


def _ctx(request: Request):
    """Return common context values."""
    return {
        "db": request.app.state.db,
        "you_id": request.app.state.you_id,
        "them_id": request.app.state.them_id,
        "your_name": request.app.state.your_name,
        "their_name": request.app.state.their_name,
        "templates": request.app.state.templates,
    }


@router.get("/deep-dives", response_class=HTMLResponse)
async def deep_dives_index(request: Request):
    c = _ctx(request)
    return c["templates"].TemplateResponse(
        "deep_dives/index.html",
        {
            "request": request,
            "active_page": "deep_dives",
            "your_name": c["your_name"],
            "their_name": c["their_name"],
        },
    )


@router.get("/deep-dives/response-time", response_class=HTMLResponse)
async def deep_dives_response_time(request: Request):
    c = _ctx(request)
    engine = AnalyticsEngine(c["db"])
    f = Filters()
    response_times = asdict(engine.response_times(c["you_id"], c["them_id"], f))

    return c["templates"].TemplateResponse(
        "deep_dives/response_time.html",
        {
            "request": request,
            "active_page": "deep_dives",
            "your_name": c["your_name"],
            "their_name": c["their_name"],
            "response_times": response_times,
            "format_duration": _format_duration,
        },
    )


@router.get("/deep-dives/communication", response_class=HTMLResponse)
async def deep_dives_communication(request: Request):
    c = _ctx(request)
    engine = AnalyticsEngine(c["db"])
    f = Filters()
    comm = asdict(engine.communication(c["you_id"], c["them_id"], f))

    return c["templates"].TemplateResponse(
        "deep_dives/communication.html",
        {
            "request": request,
            "active_page": "deep_dives",
            "your_name": c["your_name"],
            "their_name": c["their_name"],
            "comm": comm,
        },
    )


@router.get("/deep-dives/activity", response_class=HTMLResponse)
async def deep_dives_activity(request: Request):
    c = _ctx(request)
    engine = AnalyticsEngine(c["db"])
    f = Filters()
    volume = asdict(engine.volume(c["you_id"], c["them_id"], f))
    heatmap = asdict(engine.heatmap(c["you_id"], c["them_id"], f))

    return c["templates"].TemplateResponse(
        "deep_dives/activity.html",
        {
            "request": request,
            "active_page": "deep_dives",
            "your_name": c["your_name"],
            "their_name": c["their_name"],
            "volume": volume,
            "heatmap": heatmap,
        },
    )
