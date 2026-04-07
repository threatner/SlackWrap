import sys
import time
import requests

API_BASE = "https://slack.com/api"
THROTTLE_AFTER = 30  # start throttling after this many requests per minute
THROTTLE_DELAY = 1.2  # seconds to wait when throttling


def _print_status(msg: str):
    sys.stderr.write(f"\r\033[K  {msg}")
    sys.stderr.flush()


def _clear_status():
    sys.stderr.write("\r\033[K")
    sys.stderr.flush()


class SlackClient:
    def __init__(self, token: str, user_id: str):
        self.token = token
        self.user_id = user_id
        self.headers = {"Authorization": f"Bearer {token}"}
        self._user_cache: dict[str, str] = {}
        self._request_timestamps: list[float] = []

    def _throttle_if_needed(self):
        now = time.time()
        # Keep only timestamps from the last 60 seconds
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 60]
        if len(self._request_timestamps) >= THROTTLE_AFTER:
            _print_status(f"Throttling... ({len(self._request_timestamps)} requests in last 60s)")
            time.sleep(THROTTLE_DELAY)

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        self._throttle_if_needed()
        resp = requests.get(f"{API_BASE}/{endpoint}", headers=self.headers, params=params or {})

        # Handle Slack rate limit response
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            _print_status(f"Rate limited by Slack, waiting {retry_after}s...")
            time.sleep(retry_after)
            resp = requests.get(f"{API_BASE}/{endpoint}", headers=self.headers, params=params or {})

        self._request_timestamps.append(time.time())
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")
        return data

    def search_users(self, query: str) -> list[dict]:
        query_lower = query.lower()
        matches = []
        cursor = ""
        page = 0
        while True:
            page += 1
            _print_status(f"Searching users... (page {page}, {len(matches)} found)")
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("users.list", params)
            for member in data.get("members", []):
                if member.get("deleted") or member.get("is_bot"):
                    continue
                name = member.get("real_name", "").lower()
                username = member.get("name", "").lower()
                if query_lower in name or query_lower in username:
                    matches.append(member)
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        _clear_status()
        return matches

    def list_dm_channels(self) -> list[dict]:
        channels = []
        cursor = ""
        page = 0
        while True:
            page += 1
            _print_status(f"Loading DM channels... (page {page}, {len(channels)} loaded)")
            params = {"types": "im", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.list", params)
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        _clear_status()
        return channels

    def search_channels(self, query: str) -> list[dict]:
        query_lower = query.lower()
        matches = []
        cursor = ""
        page = 0
        while True:
            page += 1
            _print_status(f"Searching channels... (page {page}, {len(matches)} found)")
            params = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.list", params)
            for ch in data.get("channels", []):
                if query_lower in ch.get("name", "").lower():
                    matches.append(ch)
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        _clear_status()
        return matches

    def fetch_huddles(self, channel_id: str) -> list[dict]:
        huddles = []
        cursor = ""
        page = 0
        messages_scanned = 0
        while True:
            page += 1
            _print_status(f"Scanning messages... (page {page}, {messages_scanned} scanned, {len(huddles)} huddles found)")
            params = {"channel": channel_id, "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.history", params)
            for msg in data.get("messages", []):
                messages_scanned += 1
                if msg.get("subtype") != "huddle_thread":
                    continue
                room = msg.get("room", {})
                if not room.get("has_ended"):
                    continue
                huddles.append(msg)
            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        _clear_status()
        return huddles

    def resolve_user_name(self, user_id: str) -> str:
        if user_id == self.user_id:
            return "You"
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        data = self._get("users.info", {"user": user_id})
        name = data.get("user", {}).get("real_name", user_id)
        self._user_cache[user_id] = name
        return name
