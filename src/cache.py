import json
import os
import re
import tempfile

CACHE_VERSION = 3


class CacheManager:
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = cache_dir

    def _path(self, channel_id: str) -> str:
        safe_id = re.sub(r'[^A-Za-z0-9_-]', '', channel_id)
        return os.path.join(self.cache_dir, f"{safe_id}.json")

    def _manifest_path(self) -> str:
        return os.path.join(self.cache_dir, "_workspace_manifest.json")

    def _atomic_write_json(self, path: str, data: dict) -> None:
        """Write JSON atomically: write to .tmp then rename."""
        os.makedirs(os.path.dirname(path) or self.cache_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=os.path.dirname(path) or self.cache_dir)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.rename(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    @staticmethod
    def trim_message(msg: dict) -> dict:
        trimmed = {
            "user": msg.get("user"),
            "ts": msg.get("ts"),
            "text": msg.get("text", ""),
            "subtype": msg.get("subtype"),
        }
        trimmed["thread_ts"] = msg.get("thread_ts")
        trimmed["reply_count"] = msg.get("reply_count", 0)
        trimmed["latest_reply"] = msg.get("latest_reply")
        files = msg.get("files", [])
        trimmed["files_count"] = len(files)
        trimmed["file_types"] = [f.get("filetype", "") for f in files]
        if msg.get("reactions"):
            trimmed["reactions"] = [
                {"name": r.get("name", ""), "users": r.get("users", []), "count": r.get("count", 0)}
                for r in msg["reactions"]
            ]
        if "room" in msg:
            room = msg["room"]
            trimmed["room"] = {
                "date_start": room.get("date_start"),
                "date_end": room.get("date_end"),
                "has_ended": room.get("has_ended"),
                "participant_history": room.get("participant_history", []),
                "created_by": room.get("created_by"),
            }
        return trimmed

    @staticmethod
    def _min_ts(ts_list: list[str]) -> str:
        return min(ts_list, key=float)

    @staticmethod
    def _max_ts(ts_list: list[str]) -> str:
        return max(ts_list, key=float)

    def _migrate_v2_to_v3(self, data: dict, path: str) -> dict:
        """Add v3 fields to a v2 cache and re-persist."""
        messages = data.get("messages", [])
        all_ts = [m["ts"] for m in messages if m.get("ts")]
        data["version"] = 3
        data["oldest_cached_ts"] = self._min_ts(all_ts) if all_ts else data.get("last_ts", "0")
        data["newest_cached_ts"] = self._max_ts(all_ts) if all_ts else data.get("last_ts", "0")
        data.setdefault("threads", {})
        self._atomic_write_json(path, data)
        return data

    def load(self, channel_id: str) -> dict | None:
        path = self._path(channel_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            version = data.get("version", 0)
            if version < 2:
                os.remove(path)
                return None
            if version == 2:
                data = self._migrate_v2_to_v3(data, path)
            return data
        except (json.JSONDecodeError, KeyError):
            return None

    def save(self, channel_id: str, messages: list[dict], last_ts: str):
        os.makedirs(self.cache_dir, exist_ok=True)
        all_ts = [m["ts"] for m in messages if m.get("ts")]
        oldest = self._min_ts(all_ts) if all_ts else last_ts
        newest = self._max_ts(all_ts) if all_ts else last_ts
        data = {
            "version": CACHE_VERSION,
            "channel_id": channel_id,
            "last_ts": last_ts,
            "oldest_cached_ts": oldest,
            "newest_cached_ts": newest,
            "messages": messages,
            "threads": {},
        }
        self._atomic_write_json(self._path(channel_id), data)

    def append(self, channel_id: str, new_messages: list[dict], last_ts: str) -> list[dict]:
        existing = self.load(channel_id)
        if existing is None:
            self.save(channel_id, new_messages, last_ts)
            return new_messages
        existing["messages"].extend(new_messages)
        existing["last_ts"] = last_ts
        new_ts = [m["ts"] for m in new_messages if m.get("ts")]
        if new_ts:
            existing["newest_cached_ts"] = self._max_ts([existing.get("newest_cached_ts", "0")] + new_ts)
            existing["oldest_cached_ts"] = self._min_ts([existing.get("oldest_cached_ts", new_ts[0])] + new_ts)
        self._atomic_write_json(self._path(channel_id), existing)
        return existing["messages"]

    def save_thread_participants(self, channel_id: str, thread_ts: str, participants: list[str], latest_reply: str):
        """Persist a slim record of who replied in a given thread."""
        existing = self.load(channel_id)
        if existing is None:
            existing = {
                "version": CACHE_VERSION,
                "channel_id": channel_id,
                "last_ts": "0",
                "oldest_cached_ts": "0",
                "newest_cached_ts": "0",
                "messages": [],
                "threads": {},
            }
        existing.setdefault("threads", {})
        existing["threads"][thread_ts] = {
            "participants": list(participants),
            "latest_reply": latest_reply,
        }
        self._atomic_write_json(self._path(channel_id), existing)

    def save_manifest(self, manifest: dict) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        self._atomic_write_json(self._manifest_path(), manifest)

    def load_manifest(self) -> dict | None:
        path = self._manifest_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def clear(self, channel_id: str):
        path = self._path(channel_id)
        if os.path.exists(path):
            os.remove(path)

    def clear_all(self):
        if not os.path.exists(self.cache_dir):
            return
        for fname in os.listdir(self.cache_dir):
            if fname.endswith(".json"):
                os.remove(os.path.join(self.cache_dir, fname))
