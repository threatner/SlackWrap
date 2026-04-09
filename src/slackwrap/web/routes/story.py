from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/story")
async def story_page():
    return {"page": "story", "status": "placeholder"}
