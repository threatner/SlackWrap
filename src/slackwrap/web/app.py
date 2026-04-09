from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from slackwrap.db import Database
from slackwrap.web.routes import api, chat, deep_dives, explore, story

_HERE = Path(__file__).resolve().parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"


def create_app(
    db: Database,
    you_id: int,
    them_id: int,
    your_name: str = "You",
    their_name: str = "Them",
) -> FastAPI:
    app = FastAPI(title="SlackWrap")

    # Store shared state
    app.state.db = db
    app.state.you_id = you_id
    app.state.them_id = them_id
    app.state.your_name = your_name
    app.state.their_name = their_name

    # Jinja2 templates
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Register routers
    app.include_router(story.router)
    app.include_router(explore.router)
    app.include_router(deep_dives.router)
    app.include_router(chat.router)
    app.include_router(api.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
