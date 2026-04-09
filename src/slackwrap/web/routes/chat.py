from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(prefix="/chat")

_chat_engine = None


def _get_chat_engine(request: Request):
    global _chat_engine
    if _chat_engine is None:
        from slackwrap.ai.ollama_client import OllamaClient
        from slackwrap.ai.chat_engine import ChatEngine
        state = request.app.state
        ollama = OllamaClient()
        _chat_engine = ChatEngine(
            db=state.db,
            ollama=ollama,
            you_id=state.you_id,
            them_id=state.them_id,
            your_name=state.your_name,
            their_name=state.their_name,
        )
    return _chat_engine


@router.get("", response_class=HTMLResponse)
async def chat_page(request: Request):
    templates = request.app.state.templates
    engine = _get_chat_engine(request)
    ollama_available = engine.ollama.is_available()
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "active_page": "chat",
            "your_name": request.app.state.your_name,
            "their_name": request.app.state.their_name,
            "ollama_available": ollama_available,
        },
    )


@router.post("/ask")
async def chat_ask(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        return JSONResponse({"response": "Please enter a message.", "error": True})
    try:
        engine = _get_chat_engine(request)
        response = engine.ask(message)
        return JSONResponse({"response": response, "error": False})
    except Exception as exc:
        return JSONResponse({"response": f"Error: {exc}", "error": True})
