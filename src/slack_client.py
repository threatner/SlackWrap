import sys
import time
import requests

API_BASE = "https://slack.com/api"

# Slack rate limits per method tier (requests per minute)
# We use slightly below the documented minimum to avoid 429s
TIER_LIMITS = {
    2: {"max": 18, "label": "Tier 2"},   # Slack says 20+
    3: {"max": 45, "label": "Tier 3"},   # Slack says 50+
    4: {"max": 90, "label": "Tier 4"},   # Slack says 100+
}

# Map endpoints to their tier
ENDPOINT_TIERS = {
    "users.list": 2,
    "users.info": 4,
    "conversations.list": 2,
    "conversations.history": 3,
    "conversations.replies": 3,
    "conversations.members": 4,
    "auth.test": 4,
}


class _StatusDisplay:
    """Manages two in-place lines: progress (line 1) and throttle (line 2)."""

    def __init__(self):
        self._active = False
        self._progress = ""
        self._throttle = ""

    def _render(self):
        if not self._active:
            sys.stderr.write(f"  {self._progress}\n  {self._throttle}")
            self._active = True
        else:
            sys.stderr.write(f"\033[A\r\033[K  {self._progress}\n\r\033[K  {self._throttle}")
        sys.stderr.flush()

    def update_progress(self, msg: str):
        self._progress = msg
        self._render()

    def update_throttle(self, msg: str):
        self._throttle = msg
        self._render()

    def clear(self):
        if self._active:
            sys.stderr.write(f"\033[A\r\033[K\r\033[K")
            sys.stderr.flush()
            self._active = False
            self._progress = ""
            self._throttle = ""


_display = _StatusDisplay()


def _print_status(msg: str):
    _display.update_progress(msg)


def _clear_status():
    _display.clear()


class SlackClient:
    def __init__(self, token: str, user_id: str | None = None):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self._user_cache: dict[str, str] = {}
        self._endpoint_timestamps: dict[str, list[float]] = {}
        self.team = None
        self.username = None
        # Auto-detect user_id from token if not provided
        if user_id:
            self.user_id = user_id
        else:
            resp = requests.get(f"{API_BASE}/auth.test", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Slack auth failed: {data.get('error', 'unknown')}")
            self.user_id = data["user_id"]
            self.username = data.get("user", "")
            self.team = data.get("team", "")

    def _get_endpoint_count(self, endpoint: str) -> int:
        now = time.time()
        if endpoint not in self._endpoint_timestamps:
            self._endpoint_timestamps[endpoint] = []
        self._endpoint_timestamps[endpoint] = [
            t for t in self._endpoint_timestamps[endpoint] if now - t < 60
        ]
        return len(self._endpoint_timestamps[endpoint])

    def _throttle_if_needed(self, endpoint: str):
        tier = ENDPOINT_TIERS.get(endpoint, 3)
        tier_info = TIER_LIMITS[tier]
        max_req = tier_info["max"]

        count = self._get_endpoint_count(endpoint)

        if count >= max_req:
            # Calculate exact wait: when will the oldest request in window expire?
            oldest_ts = self._endpoint_timestamps[endpoint][0]
            wait = 60.0 - (time.time() - oldest_ts) + 0.1  # +0.1s buffer
            if wait > 0:
                _display.update_throttle(
                    f"[throttle] {count}/{max_req} {tier_info['label']} — waiting {wait:.0f}s for window to free up"
                )
                time.sleep(wait)
                # After waiting, clean up expired timestamps
                self._get_endpoint_count(endpoint)
        else:
            _display.update_throttle(f"[{tier_info['label']}] {count}/{max_req} req/min")

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        self._throttle_if_needed(endpoint)
        resp = requests.get(f"{API_BASE}/{endpoint}", headers=self.headers, params=params or {})

        # Handle 429 with retry loop
        while resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            _display.update_throttle(f"[rate-limited] Slack said wait {retry_after}s...")
            time.sleep(retry_after)
            # Clean up old timestamps after waiting
            self._get_endpoint_count(endpoint)
            resp = requests.get(f"{API_BASE}/{endpoint}", headers=self.headers, params=params or {})

        # Record this request
        if endpoint not in self._endpoint_timestamps:
            self._endpoint_timestamps[endpoint] = []
        self._endpoint_timestamps[endpoint].append(time.time())

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
                profile = member.get("profile", {})
                display_name = profile.get("display_name", "").lower()
                first_name = profile.get("first_name", "").lower()
                last_name = profile.get("last_name", "").lower()
                if query_lower in name or query_lower in username or query_lower in display_name or query_lower in first_name or query_lower in last_name:
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

    def fetch_thread_replies(self, channel_id: str, thread_ts: str) -> list[dict]:
        replies = []
        cursor = ""
        while True:
            params = {"channel": channel_id, "ts": thread_ts, "limit": 200}
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

    def fetch_messages(self, channel_id: str, oldest: str | None = None, include_threads: bool = False) -> list[dict]:
        messages = []
        cursor = ""
        page = 0
        while True:
            page += 1
            _print_status(f"Fetching messages... (page {page}, {len(messages):,} fetched)")
            params = {"channel": channel_id, "limit": 999}
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

        if include_threads:
            thread_parents = [m for m in messages if m.get("reply_count", 0) > 0]
            if thread_parents:
                existing_ts = {m["ts"] for m in messages}
                for i, parent in enumerate(thread_parents):
                    _print_status(f"Fetching threads... ({i+1}/{len(thread_parents)}, {len(messages):,} total)")
                    replies = self.fetch_thread_replies(channel_id, parent["ts"])
                    for reply in replies:
                        if reply["ts"] not in existing_ts:
                            messages.append(reply)
                            existing_ts.add(reply["ts"])

        _clear_status()
        return messages

    def fetch_huddles(self, channel_id: str) -> list[dict]:
        messages = self.fetch_messages(channel_id)
        huddles = []
        for msg in messages:
            if msg.get("subtype") != "huddle_thread":
                continue
            room = msg.get("room", {})
            if not room.get("has_ended"):
                continue
            huddles.append(msg)
        return huddles

    def list_all_channels(self) -> list[dict]:
        channels = []
        cursor = ""
        page = 0
        while True:
            page += 1
            _print_status(f"Loading channels... (page {page}, {len(channels)} loaded)")
            params = {"types": "public_channel,private_channel", "limit": 200, "exclude_archived": "true"}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.list", params)
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        _clear_status()
        return channels

    def check_channel_membership(self, channel_id: str, target_user_id: str) -> bool:
        cursor = ""
        while True:
            params = {"channel": channel_id, "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.members", params)
            if target_user_id in data.get("members", []):
                return True
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
        return False

    def find_shared_channels(self, target_user_id: str) -> list[dict]:
        all_channels = self.list_all_channels()
        shared = []
        for i, ch in enumerate(all_channels):
            _print_status(f"Checking shared channels... ({i + 1}/{len(all_channels)}, {len(shared)} shared)")
            if self.check_channel_membership(ch["id"], target_user_id):
                shared.append(ch)
        _clear_status()
        return shared

    def _extract_display_name(self, user_data: dict) -> str:
        profile = user_data.get("profile", {})
        return (
            profile.get("display_name")
            or user_data.get("real_name")
            or user_data.get("name")
            or user_data.get("id", "Unknown")
        )

    def resolve_user_name(self, user_id: str) -> str:
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        data = self._get("users.info", {"user": user_id})
        name = self._extract_display_name(data.get("user", {}))
        self._user_cache[user_id] = name
        return name
