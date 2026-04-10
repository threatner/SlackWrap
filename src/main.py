import argparse
import os
import sys
import requests
from dotenv import load_dotenv
from src.cache import CacheManager
from src.slack_client import SlackClient


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SlackWrap — Your Slack year in review")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, fetch everything fresh (don't save)")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached data before running")
    parser.add_argument("--fetch-only", action="store_true",
                        help="Fetch all in-scope conversations to .cache and exit (no analytics)")
    parser.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD",
                        help="Window start date (inclusive)")
    parser.add_argument("--to", dest="to_date", metavar="YYYY-MM-DD",
                        help="Window end date (inclusive)")
    parser.add_argument("--year", type=int, help="Shorthand for --from YYYY-01-01 --to YYYY-12-31")
    parser.add_argument("--workers", type=int, default=4,
                        help="Concurrent fetch workers (default 4, max 8)")
    parser.add_argument("--timezone", default=None,
                        help="IANA timezone for day-of-week/hour stats (default: system local)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    load_dotenv()
    token = os.getenv("SLACK_USER_TOKEN")

    if not token:
        print("Missing configuration. Create a .env file with:")
        print("  SLACK_USER_TOKEN=xoxp-your-token-here")
        print()
        print("To get the token:")
        print("  1. Go to https://api.slack.com/apps and create a new app")
        print("  2. Under OAuth & Permissions, add these User Token Scopes:")
        print("     channels:history, groups:history, im:history, mpim:history,")
        print("     users:read, channels:read, groups:read, im:read, mpim:read")
        print("  3. Install the app to your workspace")
        print("  4. Copy the User OAuth Token (starts with xoxp-)")
        sys.exit(1)

    if not token.startswith("xoxp-"):
        print("Warning: Token should start with 'xoxp-' (User OAuth Token)")
        print("  Bot tokens (xoxb-) and app tokens (xoxa-) are not supported.")

    try:
        client = SlackClient(token=token)
    except RuntimeError as e:
        print(f"\n  Authentication failed: {e}")
        print("  Check your SLACK_USER_TOKEN in .env")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"\n  Connection error: {e}")
        sys.exit(1)

    print(f"\n  Logged in as {client.username} @ {client.team}")
    cache = CacheManager()

    if args.clear_cache:
        cache.clear_all()
        print("  Cache cleared.")

    # --fetch-only: just cache data and exit
    if args.fetch_only:
        from src.orchestrators.workspace_flow import run_workspace_fetch, parse_window
        try:
            window_start_ts, window_end_ts = parse_window(
                year=args.year, from_str=args.from_date, to_str=args.to_date,
            )
        except ValueError as e:
            print(f"\n  Bad window: {e}")
            sys.exit(1)
        result = run_workspace_fetch(
            client, cache,
            window_start_ts=window_start_ts, window_end_ts=window_end_ts,
            workers=args.workers, show_progress=True,
        )
        print()
        print(f"  Fetched: {result['fetched_count']} conversations")
        print(f"  Failed:  {result['failed_count']}")
        if result['failures']:
            for f in result['failures']:
                print(f"    - {f['name']} ({f['channel_id']}): {f['error']}")
        print(f"  Cache:   .cache/")
        print(f"  Manifest: .cache/_workspace_manifest.json")
        sys.exit(0)

    # Workspace-only flags → go directly to workspace wrap
    if args.year or args.from_date or args.to_date:
        from src.orchestrators.workspace_flow import run_workspace_wrap, parse_window
        try:
            run_workspace_wrap(client, cache, args)
        except Exception as e:
            print(f"\n  Error: {e}")
            sys.exit(1)
        sys.exit(0)

    # Interactive mode menu
    print()
    print("SlackWrap")
    print("=" * 55)
    print("Choose a mode:")
    print("  1. Workspace wrap (your full Slack year-in-review)")
    print("  2. One-on-one report (deep stats with one colleague)")
    choice = input("\nChoice [1]: ").strip() or "1"

    if choice == "1":
        from src.orchestrators.workspace_flow import run_workspace_wrap
        try:
            run_workspace_wrap(client, cache, args)
        except Exception as e:
            print(f"\n  Error: {e}")
            sys.exit(1)
    elif choice == "2":
        from src.orchestrators.person_flow import run_person_flow
        run_person_flow(client, cache, args)
    else:
        print(f"Invalid choice: {choice}")
        sys.exit(1)


if __name__ == "__main__":
    main()
