from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/deep-dives")
async def deep_dives_page():
    return {"page": "deep_dives", "status": "placeholder"}
