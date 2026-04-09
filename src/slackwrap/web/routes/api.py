from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.analytics.filters import Filters

router = APIRouter(prefix="/api")


def _engine(request: Request) -> AnalyticsEngine:
    return AnalyticsEngine(request.app.state.db)


def _ids(request: Request) -> tuple[int, int]:
    return request.app.state.you_id, request.app.state.them_id


@router.get("/volume")
async def api_volume(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.volume(you_id, them_id, Filters()))


@router.get("/huddles")
async def api_huddles(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.huddles(you_id, them_id, Filters()))


@router.get("/response-times")
async def api_response_times(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.response_times(you_id, them_id, Filters()))


@router.get("/threads")
async def api_threads(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.threads(you_id, them_id, Filters()))


@router.get("/communication")
async def api_communication(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.communication(you_id, them_id, Filters()))


@router.get("/streaks")
async def api_streaks(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.streaks(you_id, them_id, Filters()))


@router.get("/trends")
async def api_trends(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.trends(you_id, them_id, Filters()))


@router.get("/heatmap")
async def api_heatmap(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.heatmap(you_id, them_id, Filters()))


@router.get("/relationship")
async def api_relationship(request: Request):
    engine = _engine(request)
    you_id, them_id = _ids(request)
    return asdict(engine.relationship(you_id, them_id, Filters()))


@router.get("/health")
async def api_health():
    return {"status": "ok"}
