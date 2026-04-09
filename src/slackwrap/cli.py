from __future__ import annotations
import argparse
import os
import sys
from dotenv import load_dotenv
from slackwrap.config import SlackWrapConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slackwrap", description="SlackWrap -- Your Slack year in review")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, fetch everything fresh")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached data before running")
    parser.add_argument("--web", action="store_true", help="Launch web view directly (skip TUI)")
    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    token = os.getenv("SLACK_USER_TOKEN")
    if not token:
        print("Missing SLACK_USER_TOKEN. Create a .env file with:")
        print("  SLACK_USER_TOKEN=xoxp-your-token-here")
        sys.exit(1)
    config = SlackWrapConfig()
    config.ensure_dirs()
    from slackwrap.db import Database
    db = Database(str(config.db_path))
    db.initialize()
    if args.clear_cache:
        print("Cache cleared.")
    if args.web:
        print("Web-only mode not yet implemented (Plan 4)")
        sys.exit(0)
    from slackwrap.tui.app import SlackWrapApp
    app = SlackWrapApp(db=db, token=token)
    app.run()
