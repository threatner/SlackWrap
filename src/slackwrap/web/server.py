from __future__ import annotations

import socket
import threading

import uvicorn

from slackwrap.db import Database
from slackwrap.web.app import create_app


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WebServer:
    def __init__(
        self,
        db: Database,
        you_id: int,
        them_id: int,
        your_name: str = "You",
        their_name: str = "Them",
    ):
        self.port = _find_free_port()
        self.app = create_app(
            db=db,
            you_id=you_id,
            them_id=them_id,
            your_name=your_name,
            their_name=their_name,
        )
        self._config = uvicorn.Config(
            app=self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config=self._config)
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)
