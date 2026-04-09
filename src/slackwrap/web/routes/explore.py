from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters

router = APIRouter()


@router.get("/explore", response_class=HTMLResponse)
async def explore_page(request: Request):
    db = request.app.state.db
    you_id = request.app.state.you_id
    them_id = request.app.state.them_id
    your_name = request.app.state.your_name
    their_name = request.app.state.their_name
    templates = request.app.state.templates

    engine = AnalyticsEngine(db)
    f = Filters()

    volume = asdict(engine.volume(you_id, them_id, f))
    heatmap = asdict(engine.heatmap(you_id, them_id, f))
    response_times = asdict(engine.response_times(you_id, them_id, f))
    comm = asdict(engine.communication(you_id, them_id, f))

    return templates.TemplateResponse(
        "explore.html",
        {
            "request": request,
            "active_page": "explore",
            "your_name": your_name,
            "their_name": their_name,
            "volume": volume,
            "heatmap": heatmap,
            "response_times": response_times,
            "comm": comm,
        },
    )
