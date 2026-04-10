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

    def test_trim_message_includes_thread_fields(self):
        msg = {
            "user": "U001", "ts": "1.0", "text": "reply",
            "subtype": None, "thread_ts": "0.5", "reply_count": 3,
        }
        trimmed = CacheManager.trim_message(msg)
        assert trimmed["thread_ts"] == "0.5"
        assert trimmed["reply_count"] == 3

    def test_trim_message_includes_file_fields(self):
        msg = {
            "user": "U001", "ts": "1.0", "text": "check this",
            "subtype": None,
            "files": [
                {"filetype": "png", "name": "screenshot.png"},
                {"filetype": "pdf", "name": "doc.pdf"},
            ],
        }
        trimmed = CacheManager.trim_message(msg)
        assert trimmed["files_count"] == 2
        assert trimmed["file_types"] == ["png", "pdf"]

    def test_trim_message_no_files_defaults(self):
        msg = {"user": "U001", "ts": "1.0", "text": "hi", "subtype": None}
        trimmed = CacheManager.trim_message(msg)
        assert trimmed["files_count"] == 0
        assert trimmed["file_types"] == []
        assert trimmed["thread_ts"] is None
        assert trimmed["reply_count"] == 0

    def test_load_clears_old_version_cache(self):
        # Save with old format (no version key)
        old_data = {
            "channel_id": "D001",
            "last_ts": "1.0",
            "messages": [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}],
        }
        path = os.path.join(self.tmpdir, "D001.json")
        with open(path, "w") as f:
            json.dump(old_data, f)

        result = self.cm.load("D001")
        assert result is None
        assert not os.path.exists(path)

    def test_load_returns_current_version(self):
        self.cm.save("D001", [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}], last_ts="1.0")
        result = self.cm.load("D001")
        assert result is not None
        assert result["version"] == 3


class TestCacheV3:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cm = CacheManager(cache_dir=self.tmpdir)

    def test_save_includes_v3_fields(self):
        messages = [
            {"user": "U001", "ts": "1.0", "text": "a", "subtype": None},
            {"user": "U002", "ts": "2.0", "text": "b", "subtype": None},
        ]
        self.cm.save("D001", messages, last_ts="2.0")
        result = self.cm.load("D001")
        assert result["version"] == 3
        assert result["oldest_cached_ts"] == "1.0"
        assert result["newest_cached_ts"] == "2.0"
        assert result["threads"] == {}

    def test_v2_cache_migrates_to_v3_on_load(self):
        v2_data = {
            "version": 2,
            "channel_id": "D001",
            "last_ts": "2.0",
            "messages": [
                {"user": "U001", "ts": "1.0", "text": "a", "subtype": None},
                {"user": "U002", "ts": "2.0", "text": "b", "subtype": None},
            ],
        }
        path = os.path.join(self.tmpdir, "D001.json")
        with open(path, "w") as f:
            json.dump(v2_data, f)
        result = self.cm.load("D001")
        assert result is not None
        assert result["version"] == 3
        assert result["oldest_cached_ts"] == "1.0"
        assert result["newest_cached_ts"] == "2.0"
        # Migration persisted to disk
        with open(path, "r") as f:
            on_disk = json.load(f)
        assert on_disk["version"] == 3

    def test_atomic_write_no_partial_files(self):
        messages = [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}]
        self.cm.save("D001", messages, last_ts="1.0")
        from unittest.mock import patch
        with patch("src.cache.json.dump", side_effect=IOError("disk full")):
            try:
                self.cm.save("D001", [{"user": "U002", "ts": "2.0", "text": "b", "subtype": None}], last_ts="2.0")
            except IOError:
                pass
        result = self.cm.load("D001")
        assert result is not None
        assert result["messages"][0]["text"] == "a"

    def test_threads_subcache_round_trip(self):
        messages = [{"user": "U001", "ts": "1.0", "text": "root", "subtype": None, "reply_count": 2}]
        self.cm.save("D001", messages, last_ts="1.0")
        self.cm.save_thread_participants("D001", thread_ts="1.0", participants=["U001", "U_ME"], latest_reply="1.5")
        result = self.cm.load("D001")
        assert "threads" in result
        assert result["threads"]["1.0"]["participants"] == ["U001", "U_ME"]
        assert result["threads"]["1.0"]["latest_reply"] == "1.5"

    def test_oldest_cached_ts_preserved_on_append(self):
        old = [{"user": "U001", "ts": "1.0", "text": "a", "subtype": None}]
        self.cm.save("D001", old, last_ts="1.0")
        new = [{"user": "U002", "ts": "5.0", "text": "b", "subtype": None}]
        self.cm.append("D001", new, last_ts="5.0")
        result = self.cm.load("D001")
        assert result["oldest_cached_ts"] == "1.0"
        assert result["newest_cached_ts"] == "5.0"
        assert len(result["messages"]) == 2

    def test_trim_message_includes_latest_reply(self):
        msg = {"user": "U001", "ts": "1.0", "text": "root", "subtype": None, "reply_count": 2, "latest_reply": "3.0"}
        trimmed = CacheManager.trim_message(msg)
        assert trimmed["latest_reply"] == "3.0"


class TestWorkspaceManifest:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cm = CacheManager(cache_dir=self.tmpdir)

    def test_save_and_load_manifest(self):
        manifest = {
            "version": 1,
            "discovered_at": 1712707200,
            "me_id": "U_ME",
            "conversations": [
                {"id": "C001", "kind": "public", "name": "engineering", "in_scope": True, "filter_reason": None},
                {"id": "D002", "kind": "im", "name": "github", "in_scope": False, "filter_reason": "bot_user"},
            ],
        }
        self.cm.save_manifest(manifest)
        loaded = self.cm.load_manifest()
        assert loaded == manifest

    def test_load_manifest_returns_none_when_missing(self):
        assert self.cm.load_manifest() is None

    def test_manifest_uses_atomic_write(self):
        manifest = {"version": 1, "conversations": []}
        self.cm.save_manifest(manifest)
        files = os.listdir(self.tmpdir)
        assert "_workspace_manifest.json" in files
        assert not any(f.endswith(".tmp") for f in files)
