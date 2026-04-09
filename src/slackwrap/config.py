from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SlackWrapConfig:
    data_dir: Path = field(default_factory=lambda: Path.home() / ".slackwrap")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "data.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
