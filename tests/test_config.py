import os
import tempfile
from pathlib import Path


def test_default_data_dir_is_home_slackwrap():
    from slackwrap.config import SlackWrapConfig

    config = SlackWrapConfig()
    expected = Path.home() / ".slackwrap"
    assert config.data_dir == expected


def test_custom_data_dir():
    from slackwrap.config import SlackWrapConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        config = SlackWrapConfig(data_dir=Path(tmpdir))
        assert config.data_dir == Path(tmpdir)


def test_db_path():
    from slackwrap.config import SlackWrapConfig

    config = SlackWrapConfig()
    assert config.db_path == Path.home() / ".slackwrap" / "data.db"


def test_ensure_dirs_creates_data_dir():
    from slackwrap.config import SlackWrapConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "slackwrap_test"
        config = SlackWrapConfig(data_dir=data_dir)
        config.ensure_dirs()
        assert data_dir.exists()
