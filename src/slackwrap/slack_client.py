from __future__ import annotations
import time
import requests

API_BASE = "https://slack.com/api"

TIER_LIMITS = {
    2: {"max": 18, "label": "Tier 2"},
    3: {"max": 45, "label": "Tier 3"},
    4: {"max": 90, "label": "Tier 4"},
}

ENDPOINT_TIERS = {
    "users.list": 2, "users.info": 4, "users.profile.get": 4,
    "users.conversations": 3, "conversations.list": 2,
    "conversations.history": 3, "conversations.replies": 3,
    "conversations.info": 3, "conversations.members": 4,
    "auth.test": 4, "team.info": 3, "files.list": 3,
    "reactions.list": 2, "pins.list": 2, "bookmarks.list": 3,
    "emoji.list": 2, "dnd.info": 3, "search.messages": 2,
    "chat.getPermalink": 4,
}


class RateLimiter:
    def __init__(self):
        self._timestamps: dict[str, list[float]] = {}

    def get_count(self, endpoint: str) -> int:
        now = time.time()
        ts = self._timestamps.get(endpoint, [])
        self._timestamps[endpoint] = [t for t in ts if now - t < 60]
        return len(self._timestamps[endpoint])

    def acquire(self, endpoint: str) -> None:
        tier = ENDPOINT_TIERS.get(endpoint, 3)
        max_req = TIER_LIMITS[tier]["max"]
        count = self.get_count(endpoint)
        if count >= max_req:
            ts = self._timestamps.get(endpoint, [])
            if ts:
                wait = 60.0 - (time.time() - ts[0]) + 0.1
                if wait > 0:
                    time.sleep(wait)
            self.get_count(endpoint)
        self._timestamps.setdefault(endpoint, []).append(time.time())

    def budget_estimate(self, calls: dict[str, int]) -> float:
        total = 0.0
        for endpoint, count in calls.items():
            tier = ENDPOINT_TIERS.get(endpoint, 3)
            max_req = TIER_LIMITS[tier]["max"]
            windows = count / max_req
            total += windows * 60
        return total


class SlackClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self._limiter = RateLimiter()
        self.user_id: str = ""
        self.username: str = ""
        self.team: str = ""
        self.team_id: str = ""
        self._authenticate()

    def _authenticate(self) -> None:
        data = self._get("auth.test")
        self.user_id = data["user_id"]
        self.username = data.get("user", "")
        self.team = data.get("team", "")
        self.team_id = data.get("team_id", "")

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        self._limiter.acquire(endpoint)
        resp = requests.get(
            f"{API_BASE}/{endpoint}", headers=self.headers,
            params=params or {}, timeout=30,
        )
        while resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            self._limiter.acquire(endpoint)
            resp = requests.get(
                f"{API_BASE}/{endpoint}", headers=self.headers,
                params=params or {}, timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error ({endpoint}): {data.get('error', 'unknown')}")
        return data

    def _paginate(self, endpoint: str, params: dict, items_key: str = "channels") -> list[dict]:
        results = []
        cursor = ""
        while True:
            p = {**params}
            if cursor:
                p["cursor"] = cursor
            data = self._get(endpoint, p)
            results.extend(data.get(items_key, []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return results

    def fetch_all_users(self) -> list[dict]:
        return self._paginate("users.list", {"limit": 200}, items_key="members")

    def fetch_user_info(self, user_id: str) -> dict:
        data = self._get("users.info", {"user": user_id})
        return data.get("user", {})

    def fetch_user_profile(self, user_id: str) -> dict:
        data = self._get("users.profile.get", {"user": user_id})
        return data.get("profile", {})

    def fetch_all_channels(self, types: str = "public_channel,private_channel") -> list[dict]:
        return self._paginate("conversations.list", {"types": types, "limit": 200, "exclude_archived": "true"})

    def fetch_dm_channels(self) -> list[dict]:
        return self._paginate("conversations.list", {"types": "im", "limit": 200})

    def fetch_conversation_info(self, channel_id: str) -> dict:
        data = self._get("conversations.info", {"channel": channel_id})
        return data.get("channel", {})

    def fetch_user_conversations(self, user_id: str) -> list[dict]:
        return self._paginate("users.conversations", {"user": user_id, "types": "public_channel,private_channel", "limit": 200})

    def find_shared_channels(self, target_user_id: str) -> list[dict]:
        my_channels = self.fetch_user_conversations(self.user_id)
        their_channels = self.fetch_user_conversations(target_user_id)
        their_ids = {ch["id"] for ch in their_channels}
        return [ch for ch in my_channels if ch["id"] in their_ids]

    def fetch_messages(self, channel_id: str, oldest: str | None = None) -> list[dict]:
        messages = []
        cursor = ""
        while True:
            params: dict = {"channel": channel_id, "limit": 999}
            if oldest:
                params["oldest"] = oldest
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.history", params)
            messages.extend(data.get("messages", []))
            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return messages

    def fetch_thread_replies(self, channel_id: str, thread_ts: str) -> list[dict]:
        replies = []
        cursor = ""
        while True:
            params: dict = {"channel": channel_id, "ts": thread_ts, "limit": 999}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.replies", params)
            replies.extend(data.get("messages", []))
            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return replies

    def fetch_messages_with_threads(self, channel_id: str, oldest: str | None = None) -> list[dict]:
        messages = self.fetch_messages(channel_id, oldest=oldest)
        thread_parents = [m for m in messages if m.get("reply_count", 0) > 0]
        existing_ts = {m["ts"] for m in messages}
        for parent in thread_parents:
            replies = self.fetch_thread_replies(channel_id, parent["ts"])
            for reply in replies:
                if reply["ts"] not in existing_ts:
                    messages.append(reply)
                    existing_ts.add(reply["ts"])
        return messages

    def fetch_reactions_for_user(self, user_id: str) -> list[dict]:
        return self._paginate("reactions.list", {"user": user_id, "limit": 200, "full": "true"}, items_key="items")

    def fetch_files(self, channel: str | None = None, user: str | None = None) -> list[dict]:
        params: dict = {"count": 100}
        if channel:
            params["channel"] = channel
        if user:
            params["user"] = user
        return self._paginate("files.list", params, items_key="files")

    def fetch_pins(self, channel_id: str) -> list[dict]:
        data = self._get("pins.list", {"channel": channel_id})
        return data.get("items", [])

    def fetch_team_info(self) -> dict:
        data = self._get("team.info")
        return data.get("team", {})

    def fetch_custom_emoji(self) -> dict[str, str]:
        data = self._get("emoji.list")
        return data.get("emoji", {})

    def fetch_dnd_info(self, user_id: str) -> dict:
        return self._get("dnd.info", {"user": user_id})

    def search_messages(self, query: str) -> list[dict]:
        messages = []
        page = 1
        while True:
            data = self._get("search.messages", {"query": query, "count": 100, "page": page})
            matches = data.get("messages", {}).get("matches", [])
            messages.extend(matches)
            total = data.get("messages", {}).get("total", 0)
            if len(messages) >= total:
                break
            page += 1
        return messages

    def get_permalink(self, channel_id: str, message_ts: str) -> str:
        data = self._get("chat.getPermalink", {"channel": channel_id, "message_ts": message_ts})
        return data.get("permalink", "")

    def search_users(self, query: str) -> list[dict]:
        query_lower = query.lower()
        all_users = self.fetch_all_users()
        matches = []
        for member in all_users:
            if member.get("deleted") or member.get("is_bot"):
                continue
            searchable = " ".join([
                member.get("real_name", ""),
                member.get("name", ""),
                member.get("profile", {}).get("display_name", ""),
            ]).lower()
            if query_lower in searchable:
                matches.append(member)
        return matches
