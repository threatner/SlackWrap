"""
Per-person interactive flow — lifted from main.py.

This preserves the existing v1 behavior: search → select → fetch → report.
Uses the existing formatters (combined_report, html_report) via the old
dict-based stats interfaces. The new engine is NOT used here yet — that
migration happens when we unify the HTML theme in Phase 6.
"""
import os
import sys

from src.cache import CacheManager
from src.slack_client import SlackClient
from src.report import extract_huddles, compute_stats, format_report
from src.message_analytics import compute_message_stats, format_message_report
from src.combined_report import format_combined_report
from src.html_report import generate_html_report


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
            results.append({
                "channel_id": dm_id,
                "label": f"{user['real_name']} (DM)",
                "type": "dm",
                "target_user_id": user["id"],
                "target_name": user["real_name"],
            })
    for ch in channels:
        results.append({
            "channel_id": ch["id"],
            "label": f"#{ch['name']} (channel)",
            "type": "channel",
        })
    return results


def fetch_with_cache(
    client: SlackClient,
    cache: CacheManager,
    channel_id: str,
    use_cache: bool,
    label: str = "",
) -> list[dict]:
    prefix = f"  [{label}] " if label else "  "

    if not use_cache:
        print(f"{prefix}(cache disabled)")
        raw = client.fetch_messages(channel_id, include_threads=True)
        return [CacheManager.trim_message(m) for m in raw]

    cached = cache.load(channel_id)
    if cached is not None:
        last_ts = cached["last_ts"]
        print(f"{prefix}Cache: {len(cached['messages']):,} msgs, fetching new...")
        new_raw = client.fetch_messages(channel_id, oldest=last_ts, include_threads=True)
        existing_ts = {m["ts"] for m in cached["messages"]}
        new_msgs = [CacheManager.trim_message(m) for m in new_raw if m.get("ts") not in existing_ts]
        if new_msgs:
            latest_new_ts = max(m["ts"] for m in new_msgs)
            latest_new_ts = max(latest_new_ts, last_ts)
            merged = cache.append(channel_id, new_msgs, last_ts=latest_new_ts)
            print(f"{prefix}+{len(new_msgs):,} new messages")
        else:
            merged = cached["messages"]
            print(f"{prefix}Up to date")
        return merged
    else:
        print(f"{prefix}No cache, fetching all...")
        raw = client.fetch_messages(channel_id, include_threads=True)
        trimmed = [CacheManager.trim_message(m) for m in raw]
        if trimmed:
            latest_ts = max(m["ts"] for m in trimmed)
            cache.save(channel_id, trimmed, last_ts=latest_ts)
            print(f"{prefix}Cached {len(trimmed):,} messages")
        return trimmed


def select_shared_channels(client: SlackClient, target_user_id: str, target_name: str) -> list[dict]:
    print(f"\nFinding channels shared with {target_name}...")
    shared = client.find_shared_channels(target_user_id)
    if not shared:
        print("  No shared channels found.")
        return []
    print(f"\n  Found {len(shared)} shared channels:")
    for i, ch in enumerate(shared, 1):
        print(f"    {i}. #{ch['name']}")
    print(f"    a. All")
    print(f"    n. None (DM only)")
    print()
    choice = input("  Select (comma-separated numbers, 'a' for all, 'n' for none): ").strip().lower()
    if choice == "n" or choice == "":
        return []
    if choice == "a":
        return shared
    selected = []
    for part in choice.split(","):
        part = part.strip()
        try:
            idx = int(part) - 1
            if 0 <= idx < len(shared):
                selected.append(shared[idx])
        except ValueError:
            continue
    return selected


def run_person_flow(client: SlackClient, cache: CacheManager, args) -> None:
    """Run the existing v1 per-person interactive flow."""
    user_id = client.user_id
    use_cache = not args.no_cache

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
    is_dm = selected.get("type") == "dm"
    target_user_id = selected.get("target_user_id")
    target_name = selected.get("target_name", "")

    extra_channels = []
    if is_dm:
        include = input(f"\nInclude shared channels with {target_name}? (y/n): ").strip().lower()
        if include == "y":
            extra_channels = select_shared_channels(client, target_user_id, target_name)

    label = selected["label"]

    print(f"\nFetching data...")
    all_messages = fetch_with_cache(client, cache, selected["channel_id"], use_cache, label="DM")

    for ch in extra_channels:
        ch_label = f"#{ch['name']}"
        ch_messages = fetch_with_cache(client, cache, ch["id"], use_cache, label=ch_label)
        all_messages.extend(ch_messages)

    sources_label = label
    if extra_channels:
        ch_names = ", ".join(f"#{ch['name']}" for ch in extra_channels)
        sources_label = f"{label} + {ch_names}"

    your_name = client.resolve_user_name(user_id)
    their_name = target_name if is_dm else "Them"
    filter_target = target_user_id if extra_channels else None

    huddles = extract_huddles(all_messages)
    h_stats = compute_stats(huddles, user_id, filter_target)
    m_stats = compute_message_stats(all_messages, user_id, filter_target)

    print(format_combined_report(h_stats, m_stats, sources_label, your_name, their_name))

    html_path = generate_html_report(h_stats, m_stats, sources_label, your_name, their_name)
    abs_path = os.path.abspath(html_path)
    if sys.platform == "win32":
        file_url = f"file:///{abs_path.replace(os.sep, '/')}"
    else:
        file_url = f"file://{abs_path}"
    print(f"\n  HTML report: {file_url}")
