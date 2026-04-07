import argparse
import os
import sys
from dotenv import load_dotenv
from src.cache import CacheManager
from src.slack_client import SlackClient
from src.report import extract_huddles, compute_stats, format_report
from src.message_analytics import compute_message_stats, format_message_report
from src.combined_report import format_combined_report


def build_search_results(
    users: list[dict],
    dm_channels: list[dict],
    channels: list[dict],
) -> list[dict]:
    dm_by_user = {ch["user"]: ch["id"] for ch in dm_channels}
    results = []
    for user in users:
        dm_id = dm_by_user.get(user["id"])
        if dm_id:
            results.append({"channel_id": dm_id, "label": f"{user['real_name']} (DM)"})
    for ch in channels:
        results.append({"channel_id": ch["id"], "label": f"#{ch['name']} (channel)"})
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Slack Huddle & Message Analytics")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, fetch everything fresh (don't save)")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached data before running")
    return parser.parse_args(argv)


def fetch_with_cache(
    client: SlackClient,
    cache: CacheManager,
    channel_id: str,
    use_cache: bool,
) -> list[dict]:
    if not use_cache:
        print("  (cache disabled)")
        raw = client.fetch_messages(channel_id)
        return [CacheManager.trim_message(m) for m in raw]

    cached = cache.load(channel_id)
    if cached is not None:
        last_ts = cached["last_ts"]
        print(f"  Cache found: {len(cached['messages']):,} messages up to {last_ts}")
        print("  Fetching new messages...")
        new_raw = client.fetch_messages(channel_id, oldest=last_ts)
        # conversations.history with oldest returns messages with ts > oldest,
        # but may include the boundary message. Deduplicate by ts.
        existing_ts = {m["ts"] for m in cached["messages"]}
        new_msgs = [CacheManager.trim_message(m) for m in new_raw if m.get("ts") not in existing_ts]
        if new_msgs:
            cache.append(channel_id, new_msgs, last_ts=new_msgs[0]["ts"])
            print(f"  Added {len(new_msgs):,} new messages to cache")
        else:
            print("  Cache is up to date")
        updated = cache.load(channel_id)
        return updated["messages"]
    else:
        print("  No cache found, fetching all messages (this may take a while)...")
        raw = client.fetch_messages(channel_id)
        trimmed = [CacheManager.trim_message(m) for m in raw]
        if trimmed:
            # conversations.history returns newest first, so first element has highest ts
            latest_ts = trimmed[0]["ts"]
            cache.save(channel_id, trimmed, last_ts=latest_ts)
            print(f"  Cached {len(trimmed):,} messages")
        return trimmed


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    load_dotenv()
    token = os.getenv("SLACK_USER_TOKEN")
    user_id = os.getenv("SLACK_USER_ID")

    if not token or not user_id:
        print("Missing configuration. Create a .env file with:")
        print("  SLACK_USER_TOKEN=xoxp-your-token-here")
        print("  SLACK_USER_ID=U_YOUR_USER_ID")
        print()
        print("To get these values:")
        print("  1. Go to https://api.slack.com/apps and create a new app")
        print("  2. Under OAuth & Permissions, add these User Token Scopes:")
        print("     channels:history, groups:history, im:history,")
        print("     users:read, channels:read, groups:read, im:read")
        print("  3. Install the app to your workspace")
        print("  4. Copy the User OAuth Token (starts with xoxp-)")
        print("  5. Find your User ID in Slack (Profile > ... > Copy member ID)")
        sys.exit(1)

    client = SlackClient(token=token, user_id=user_id)
    cache = CacheManager()

    if args.clear_cache:
        cache.clear_all()
        print("Cache cleared.")

    query = input("\nSearch for a person or channel: ").strip()
    if not query:
        print("No search query entered.")
        sys.exit(1)

    print(f"\nSearching for '{query}'...")
    users = client.search_users(query)
    dm_channels = client.list_dm_channels()
    channels = client.search_channels(query)

    results = build_search_results(users, dm_channels, channels)
    if not results:
        print("No matches found.")
        sys.exit(1)

    print()
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['label']}")
    print()

    choice = input(f"Select [1-{len(results)}]: ").strip()
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(results):
            raise ValueError
    except ValueError:
        print("Invalid selection.")
        sys.exit(1)

    selected = results[idx]

    # Analytics type selection
    print(f"\nWhat would you like to analyze for {selected['label']}?")
    print("  1. Huddle Time")
    print("  2. Message Analytics")
    print("  3. Both")
    print()
    analytics_choice = input("Select [1-3]: ").strip()

    print(f"\nFetching data from {selected['label']}...")
    use_cache = not args.no_cache
    messages = fetch_with_cache(client, cache, selected["channel_id"], use_cache)

    if analytics_choice == "2":
        stats = compute_message_stats(messages, user_id)
        print(format_message_report(stats, selected["label"]))
    elif analytics_choice == "3":
        huddles = extract_huddles(messages)
        h_stats = compute_stats(huddles, user_id)
        m_stats = compute_message_stats(messages, user_id)
        print(format_combined_report(h_stats, m_stats, selected["label"]))
    else:
        huddles = extract_huddles(messages)
        stats = compute_stats(huddles, user_id)
        print(format_report(stats, selected["label"], client.resolve_user_name))


if __name__ == "__main__":
    main()
