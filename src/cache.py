import json
import os

CACHE_VERSION = 2


class CacheManager:
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = cache_dir

    def _path(self, channel_id: str) -> str:
        return os.path.join(self.cache_dir, f"{channel_id}.json")

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

    def load(self, channel_id: str) -> dict | None:
        path = self._path(channel_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if data.get("version", 0) < CACHE_VERSION:
                os.remove(path)
                return None
            return data
        except (json.JSONDecodeError, KeyError):
            return None

    def save(self, channel_id: str, messages: list[dict], last_ts: str):
        os.makedirs(self.cache_dir, exist_ok=True)
        data = {
            "version": CACHE_VERSION,
            "channel_id": channel_id,
            "last_ts": last_ts,
            "messages": messages,
        }
        with open(self._path(channel_id), "w") as f:
            json.dump(data, f)

    def append(self, channel_id: str, new_messages: list[dict], last_ts: str) -> list[dict]:
        existing = self.load(channel_id)
        if existing is None:
            self.save(channel_id, new_messages, last_ts)
            return new_messages
        existing["messages"].extend(new_messages)
        existing["last_ts"] = last_ts
        with open(self._path(channel_id), "w") as f:
            json.dump(existing, f)
        return existing["messages"]

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
