from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/explore")
async def explore_page():
    return {"page": "explore", "status": "placeholder"}
