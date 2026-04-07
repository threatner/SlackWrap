import time
import requests

API_BASE = "https://slack.com/api"
RATE_LIMIT_DELAY = 1.2  # seconds between paginated requests


class SlackClient:
    def __init__(self, token: str, user_id: str):
        self.token = token
        self.user_id = user_id
        self.headers = {"Authorization": f"Bearer {token}"}
        self._user_cache: dict[str, str] = {}

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        resp = requests.get(f"{API_BASE}/{endpoint}", headers=self.headers, params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error', 'unknown')}")
        return data

    def search_users(self, query: str) -> list[dict]:
        query_lower = query.lower()
        matches = []
        cursor = ""
        while True:
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
            time.sleep(RATE_LIMIT_DELAY)
        return matches

    def list_dm_channels(self) -> list[dict]:
        channels = []
        cursor = ""
        while True:
            params = {"types": "im", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.list", params)
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            time.sleep(RATE_LIMIT_DELAY)
        return channels

    def search_channels(self, query: str) -> list[dict]:
        query_lower = query.lower()
        matches = []
        cursor = ""
        while True:
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
            time.sleep(RATE_LIMIT_DELAY)
        return matches
