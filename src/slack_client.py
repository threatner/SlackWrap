import sys
import time
import requests

API_BASE = "https://slack.com/api"
THROTTLE_AFTER = 30  # start throttling after this many requests per minute
THROTTLE_DELAY = 1.2  # seconds to wait when throttling


class _StatusDisplay:
    """Manages two in-place lines: progress (line 1) and throttle (line 2)."""

    def __init__(self):
        self._active = False
        self._progress = ""
        self._throttle = ""

    def _render(self):
        if not self._active:
            # First render: print both lines
            sys.stderr.write(f"  {self._progress}\n  {self._throttle}")
            self._active = True
        else:
            # Move up 1 line, clear, write progress, move down, clear, write throttle
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
            # Clear both lines
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
    def __init__(self, token: str, user_id: str):
        self.token = token
        self.user_id = user_id
        self.headers = {"Authorization": f"Bearer {token}"}
        self._user_cache: dict[str, str] = {}
        self._request_timestamps: list[float] = []

    def _throttle_if_needed(self):
        now = time.time()
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 60]
        req_count = len(self._request_timestamps)
        if req_count >= THROTTLE_AFTER:
            _display.update_throttle(f"[throttle] {req_count} req/60s — pausing {THROTTLE_DELAY}s")
            time.sleep(THROTTLE_DELAY)
        elif req_count > 0:
            _display.update_throttle(f"[requests] {req_count}/{THROTTLE_AFTER} in last 60s")
        else:
            _display.update_throttle("")

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        self._throttle_if_needed()
        resp = requests.get(f"{API_BASE}/{endpoint}", headers=self.headers, params=params or {})

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            _display.update_throttle(f"[rate-limited] Slack said wait {retry_after}s...")
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

    def fetch_messages(self, channel_id: str, oldest: str | None = None) -> list[dict]:
        messages = []
        cursor = ""
        page = 0
        while True:
            page += 1
            _print_status(f"Fetching messages... (page {page}, {len(messages)} fetched)")
            params = {"channel": channel_id, "limit": 200}
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

    def resolve_user_name(self, user_id: str) -> str:
        if user_id == self.user_id:
            return "You"
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        data = self._get("users.info", {"user": user_id})
        name = data.get("user", {}).get("real_name", user_id)
        self._user_cache[user_id] = name
        return name
