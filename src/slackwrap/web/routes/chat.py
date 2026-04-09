from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/chat")
async def chat_page():
    return {"page": "chat", "status": "placeholder"}
