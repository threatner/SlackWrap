import json
import os
import tempfile
from src.cache import CacheManager


class TestCacheManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cm = CacheManager(cache_dir=self.tmpdir)

    def test_no_cache_returns_none(self):
        result = self.cm.load("D001")
        assert result is None

    def test_save_and_load(self):
        messages = [
            {"user": "U001", "ts": "1700000000.000000", "text": "hello", "subtype": None},
            {"user": "U002", "ts": "1700000060.000000", "text": "hey!", "subtype": None},
        ]
        self.cm.save("D001", messages, last_ts="1700000060.000000")
        result = self.cm.load("D001")
        assert result is not None
        assert result["last_ts"] == "1700000060.000000"
        assert len(result["messages"]) == 2
        assert result["messages"][0]["text"] == "hello"

    def test_append_merges_new_messages(self):
        old = [{"user": "U001", "ts": "1700000000.000000", "text": "hello", "subtype": None}]
        self.cm.save("D001", old, last_ts="1700000000.000000")
        new = [{"user": "U002", "ts": "1700000060.000000", "text": "hey!", "subtype": None}]
        self.cm.append("D001", new, last_ts="1700000060.000000")
        result = self.cm.load("D001")
        assert len(result["messages"]) == 2
        assert result["last_ts"] == "1700000060.000000"

    def test_clear_specific_channel(self):
        self.cm.save("D001", [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}], last_ts="1.0")
        self.cm.save("D002", [{"user": "U001", "ts": "2.0", "text": "b", "subtype": None}], last_ts="2.0")
        self.cm.clear("D001")
        assert self.cm.load("D001") is None
        assert self.cm.load("D002") is not None

    def test_clear_all(self):
        self.cm.save("D001", [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}], last_ts="1.0")
        self.cm.save("D002", [{"user": "U001", "ts": "2.0", "text": "b", "subtype": None}], last_ts="2.0")
        self.cm.clear_all()
        assert self.cm.load("D001") is None
        assert self.cm.load("D002") is None

    def test_trim_message_strips_extra_fields(self):
        msg = {
            "user": "U001", "ts": "1700000000.000000", "text": "hello",
            "subtype": "huddle_thread",
            "room": {"date_start": 100, "date_end": 200, "has_ended": True, "participant_history": ["U001"], "created_by": "U001"},
            "blocks": [{"type": "rich_text"}], "team": "T123", "extra_field": "drop",
        }
        trimmed = CacheManager.trim_message(msg)
        assert trimmed["user"] == "U001"
        assert trimmed["room"]["date_start"] == 100
        assert "blocks" not in trimmed
        assert "extra_field" not in trimmed

    def test_trim_message_without_room(self):
        msg = {"user": "U001", "ts": "1.0", "text": "hi", "type": "message"}
        trimmed = CacheManager.trim_message(msg)
        assert "room" not in trimmed

    def test_corrupted_cache_returns_none(self):
        path = os.path.join(self.tmpdir, "D001.json")
        with open(path, "w") as f:
            f.write("not valid json{{{")
        result = self.cm.load("D001")
        assert result is None
