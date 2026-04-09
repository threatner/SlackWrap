from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/health")
async def api_health():
    return {"page": "api", "status": "placeholder"}
