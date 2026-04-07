import os
import sys
from dotenv import load_dotenv
from src.slack_client import SlackClient
from src.report import compute_stats, format_report


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


def main():
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
    print(f"\nFetching huddles from {selected['label']}...")
    huddles = client.fetch_huddles(selected["channel_id"])

    stats = compute_stats(huddles, user_id)
    output = format_report(stats, selected["label"], client.resolve_user_name)
    print(output)


if __name__ == "__main__":
    main()
