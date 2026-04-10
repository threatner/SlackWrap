import tempfile
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone

from src.cache import CacheManager
from src.engine.models import UserDirectory
from src.orchestrators.workspace_flow import (
    discover_workspace,
    persist_manifest,
    fetch_conversation_messages,
    walk_threads_for_conversation,
    run_workspace_fetch,
    parse_window,
    load_conversation_from_cache,
)


def _client(users, conversations):
    client = MagicMock()
    client.user_id = "U_ME"
    client.list_users.return_value = users
    client.list_conversations.return_value = conversations
    return client


USERS = [
    {"id": "U_ME", "name": "me", "real_name": "Me", "is_bot": False, "deleted": False, "profile": {"display_name": "Me"}},
    {"id": "U001", "name": "alice", "real_name": "Alice", "is_bot": False, "deleted": False, "profile": {"display_name": "Alice"}},
    {"id": "U002", "name": "bob", "real_name": "Bob", "is_bot": False, "deleted": False, "profile": {"display_name": "Bob"}},
    {"id": "BOT", "name": "github", "real_name": "GitHub", "is_bot": True, "deleted": False, "profile": {"display_name": "GitHub"}},
]


# -----------------------------------------------------------------------
# Discovery
# -----------------------------------------------------------------------

class TestDiscoverWorkspace:
    def test_filters_bot_dms(self):
        convs = [
            {"id": "D001", "is_im": True, "user": "U001"},
            {"id": "D002", "is_im": True, "user": "BOT"},
        ]
        c = _client(USERS, convs)
        directory, in_scope, out_of_scope = discover_workspace(c)
        assert isinstance(directory, UserDirectory)
        assert len(in_scope) == 1
        assert in_scope[0]["id"] == "D001"
        assert out_of_scope[0]["filter_reason"] == "bot_user"

    def test_filters_non_member_channels(self):
        convs = [
            {"id": "C001", "name": "eng", "is_channel": True, "is_member": True, "is_archived": False},
            {"id": "C002", "name": "random", "is_channel": True, "is_member": False, "is_archived": False},
        ]
        c = _client(USERS, convs)
        _, in_scope, out_of_scope = discover_workspace(c)
        assert len(in_scope) == 1
        assert out_of_scope[0]["filter_reason"] == "not_a_member"

    def test_includes_archived_member_channels(self):
        convs = [{"id": "C001", "name": "old", "is_channel": True, "is_member": True, "is_archived": True}]
        c = _client(USERS, convs)
        _, in_scope, _ = discover_workspace(c)
        assert len(in_scope) == 1

    def test_includes_mpim_private_connect(self):
        convs = [
            {"id": "G001", "name": "mpdm-me-alice-bob", "is_mpim": True, "is_member": True},
            {"id": "C002", "name": "secret", "is_group": True, "is_private": True, "is_member": True},
            {"id": "C003", "name": "shared", "is_channel": True, "is_member": True, "is_ext_shared": True},
        ]
        c = _client(USERS, convs)
        _, in_scope, _ = discover_workspace(c)
        assert {e["id"] for e in in_scope} == {"G001", "C002", "C003"}

    def test_directory_has_all_users_including_bots(self):
        c = _client(USERS, [])
        directory, _, _ = discover_workspace(c)
        assert "BOT" in directory.users
        assert directory.users["BOT"].is_bot is True


# -----------------------------------------------------------------------
# Manifest
# -----------------------------------------------------------------------

class TestPersistManifest:
    def test_writes_manifest(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        in_scope = [{"id": "C001", "kind": "public", "name": "eng", "is_archived": False, "counterparty_id": None, "raw": {}}]
        out_of_scope = [{"id": "D002", "kind": "im", "name": "github", "filter_reason": "bot_user", "raw": {}}]
        persist_manifest(cache, me_id="U_ME", in_scope=in_scope, out_of_scope=out_of_scope)
        manifest = cache.load_manifest()
        assert manifest["me_id"] == "U_ME"
        assert len(manifest["conversations"]) == 2

    def test_preserves_per_channel_cache_state(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        existing = {
            "version": 1, "discovered_at": 100, "me_id": "U_ME",
            "conversations": [
                {"id": "C001", "kind": "public", "name": "eng", "in_scope": True,
                 "filter_reason": None, "oldest_cached_ts": "1.0", "newest_cached_ts": "10.0", "last_fetched_ts": 200},
            ],
        }
        cache.save_manifest(existing)
        in_scope = [{"id": "C001", "kind": "public", "name": "eng", "is_archived": False, "counterparty_id": None, "raw": {}}]
        persist_manifest(cache, me_id="U_ME", in_scope=in_scope, out_of_scope=[])
        manifest = cache.load_manifest()
        c1 = next(c for c in manifest["conversations"] if c["id"] == "C001")
        assert c1["oldest_cached_ts"] == "1.0"
        assert c1["newest_cached_ts"] == "10.0"


# -----------------------------------------------------------------------
# Fetch
# -----------------------------------------------------------------------

class TestFetchConversationMessages:
    def test_fetches_full_history_when_no_cache(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        client = MagicMock()
        client.fetch_messages.return_value = [
            {"user": "U001", "ts": "100.0", "text": "hi", "type": "message"},
            {"user": "U_ME", "ts": "200.0", "text": "hey", "type": "message"},
        ]
        msgs = fetch_conversation_messages(client, cache, "C001", "50.0", "999.0")
        assert len(msgs) == 2

    def test_incremental_fetch_uses_newest_cached_ts(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        cache.save("C001", [
            {"user": "U001", "ts": "100.0", "text": "old", "subtype": None},
            {"user": "U_ME", "ts": "200.0", "text": "older", "subtype": None},
        ], last_ts="200.0")
        client = MagicMock()
        client.fetch_messages.return_value = [
            {"user": "U_ME", "ts": "300.0", "text": "new", "type": "message"},
        ]
        msgs = fetch_conversation_messages(client, cache, "C001", "50.0", "999.0")
        call_kwargs = client.fetch_messages.call_args[1]
        assert call_kwargs["oldest"] == "200.0"
        assert len(msgs) == 3

    def test_persists_to_cache(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        client = MagicMock()
        client.fetch_messages.return_value = [
            {"user": "U001", "ts": "100.0", "text": "hi", "type": "message"},
        ]
        fetch_conversation_messages(client, cache, "C001", "50.0", "999.0")
        assert cache.load("C001") is not None


class TestBackfillWindow:
    def test_backfills_when_window_extends_earlier(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        cache.save("C001", [
            {"user": "U001", "ts": "300.0", "text": "march", "subtype": None},
            {"user": "U_ME", "ts": "1200.0", "text": "dec", "subtype": None},
        ], last_ts="1200.0")
        client = MagicMock()
        backfill_msgs = [
            {"user": "U_ME", "ts": "100.0", "text": "jan", "type": "message"},
            {"user": "U001", "ts": "200.0", "text": "feb", "type": "message"},
        ]
        client.fetch_messages.side_effect = [backfill_msgs, []]
        msgs = fetch_conversation_messages(client, cache, "C001", "50.0", "9999.0")
        assert client.fetch_messages.call_count == 2
        first_call = client.fetch_messages.call_args_list[0]
        assert first_call[1]["oldest"] == "50.0"
        assert first_call[1].get("latest") == "300.0"
        assert len(msgs) == 4

    def test_no_backfill_when_window_inside_cache(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        cache.save("C001", [
            {"user": "U001", "ts": "100.0", "text": "early", "subtype": None},
            {"user": "U_ME", "ts": "1000.0", "text": "late", "subtype": None},
        ], last_ts="1000.0")
        client = MagicMock()
        client.fetch_messages.return_value = []
        fetch_conversation_messages(client, cache, "C001", "200.0", "9999.0")
        assert client.fetch_messages.call_count == 1


# -----------------------------------------------------------------------
# Thread walker
# -----------------------------------------------------------------------

class TestWalkThreads:
    def test_walks_only_threads_user_participated_in(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        cache.save("C001", [
            {"user": "U_ME", "ts": "100.0", "text": "my thread", "subtype": None, "reply_count": 2, "latest_reply": "200.0"},
            {"user": "U_ME", "ts": "600.0", "text": "my reply", "subtype": None, "thread_ts": "500.0", "reply_count": 0},
            {"user": "U001", "ts": "700.0", "text": "other thread", "subtype": None, "reply_count": 1, "latest_reply": "750.0"},
            {"user": "U_ME", "ts": "800.0", "text": "regular msg", "subtype": None, "reply_count": 0},
        ], last_ts="800.0")
        client = MagicMock()

        def fake_replies(channel_id, thread_ts):
            if thread_ts == "100.0":
                return [
                    {"user": "U_ME", "ts": "100.0", "thread_ts": "100.0"},
                    {"user": "U001", "ts": "150.0", "thread_ts": "100.0"},
                    {"user": "U002", "ts": "200.0", "thread_ts": "100.0"},
                ]
            if thread_ts == "500.0":
                return [
                    {"user": "U001", "ts": "500.0", "thread_ts": "500.0"},
                    {"user": "U_ME", "ts": "600.0", "thread_ts": "500.0"},
                ]
            return []
        client.fetch_thread_replies.side_effect = fake_replies

        walk_threads_for_conversation(client, cache, "C001", "U_ME")
        assert client.fetch_thread_replies.call_count == 2
        cached = cache.load("C001")
        assert set(cached["threads"]["100.0"]["participants"]) == {"U_ME", "U001", "U002"}
        assert set(cached["threads"]["500.0"]["participants"]) == {"U_ME", "U001"}

    def test_skips_already_walked_threads(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        cache.save("C001", [
            {"user": "U_ME", "ts": "100.0", "text": "root", "subtype": None, "reply_count": 1, "latest_reply": "150.0"},
        ], last_ts="100.0")
        cache.save_thread_participants("C001", "100.0", ["U_ME", "U001"], "150.0")
        client = MagicMock()
        walk_threads_for_conversation(client, cache, "C001", "U_ME")
        assert client.fetch_thread_replies.call_count == 0

    def test_rewalks_when_latest_reply_changed(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        cache.save("C001", [
            {"user": "U_ME", "ts": "100.0", "text": "root", "subtype": None, "reply_count": 3, "latest_reply": "200.0"},
        ], last_ts="100.0")
        cache.save_thread_participants("C001", "100.0", ["U_ME", "U001"], "150.0")
        client = MagicMock()
        client.fetch_thread_replies.return_value = [
            {"user": "U_ME", "ts": "100.0", "thread_ts": "100.0"},
            {"user": "U001", "ts": "150.0", "thread_ts": "100.0"},
            {"user": "U002", "ts": "200.0", "thread_ts": "100.0"},
        ]
        walk_threads_for_conversation(client, cache, "C001", "U_ME")
        assert client.fetch_thread_replies.call_count == 1
        cached = cache.load("C001")
        assert set(cached["threads"]["100.0"]["participants"]) == {"U_ME", "U001", "U002"}


# -----------------------------------------------------------------------
# Conversation loader
# -----------------------------------------------------------------------

class TestLoadConversation:
    def test_loads_from_cache(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        cache.save("D001", [
            {"user": "U001", "ts": "100.0", "text": "hi", "subtype": None},
            {"user": "U_ME", "ts": "200.0", "text": "hey", "subtype": None},
            {"user": "U_ME", "ts": "300.0", "text": "huddle", "subtype": "huddle_thread",
             "room": {"date_start": 100, "date_end": 200, "has_ended": True,
                      "participant_history": ["U_ME", "U001"], "created_by": "U_ME"}},
        ], last_ts="300.0")
        entry = {"id": "D001", "kind": "im", "name": "Alice", "is_archived": False, "counterparty_id": "U001"}
        conv = load_conversation_from_cache(cache, entry, frozenset({"U_ME", "U001"}))
        assert conv.id == "D001"
        assert conv.kind == "im"
        assert len(conv.messages) == 3
        assert len(conv.huddles) == 1
        assert conv.huddles[0].duration_seconds == 100


# -----------------------------------------------------------------------
# Window parsing
# -----------------------------------------------------------------------

class TestParseWindow:
    def test_default_trailing_365d(self):
        now = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        start, end = parse_window(year=None, from_str=None, to_str=None, now=now)
        assert end == f"{now.timestamp():.6f}"
        expected_start = (now - timedelta(days=365)).timestamp()
        assert start == f"{expected_start:.6f}"

    def test_year_flag(self):
        start, end = parse_window(year=2025, from_str=None, to_str=None)
        assert start == f"{datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp():.6f}"
        assert end.startswith("1767225599")

    def test_explicit_from_to(self):
        start, end = parse_window(year=None, from_str="2025-06-01", to_str="2025-06-30")
        assert start == f"{datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp():.6f}"

    def test_from_after_to_raises(self):
        try:
            parse_window(year=None, from_str="2025-12-01", to_str="2025-01-01")
            assert False, "should raise"
        except ValueError as e:
            assert "after" in str(e).lower()


# -----------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------

class TestRunWorkspaceFetch:
    def test_full_pipeline(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        client = MagicMock()
        client.user_id = "U_ME"
        client.list_users.return_value = USERS
        client.list_conversations.return_value = [
            {"id": "D001", "is_im": True, "user": "U001"},
            {"id": "D002", "is_im": True, "user": "BOT"},
            {"id": "C001", "name": "eng", "is_channel": True, "is_member": True, "is_archived": False},
        ]
        client.fetch_messages.return_value = [
            {"user": "U001", "ts": "100.0", "text": "hi", "type": "message"},
        ]
        client.fetch_thread_replies.return_value = []

        result = run_workspace_fetch(client, cache, "50.0", "999.0", workers=1, show_progress=False)
        assert result["fetched_count"] == 2
        assert result["failed_count"] == 0
        manifest = cache.load_manifest()
        in_scope_ids = {c["id"] for c in manifest["conversations"] if c["in_scope"]}
        assert in_scope_ids == {"D001", "C001"}

    def test_isolates_per_channel_errors(self):
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        client = MagicMock()
        client.user_id = "U_ME"
        client.list_users.return_value = USERS[:2]
        client.list_conversations.return_value = [
            {"id": "D001", "is_im": True, "user": "U001"},
            {"id": "C001", "name": "secret", "is_channel": True, "is_member": True, "is_archived": False},
        ]

        def fake_fetch(channel_id, **kwargs):
            if channel_id == "C001":
                raise RuntimeError("missing_scope")
            return [{"user": "U001", "ts": "100.0", "text": "hi", "type": "message"}]
        client.fetch_messages.side_effect = fake_fetch
        client.fetch_thread_replies.return_value = []

        result = run_workspace_fetch(client, cache, "50.0", "999.0", workers=1, show_progress=False)
        assert result["fetched_count"] == 1
        assert result["failed_count"] == 1
        assert cache.load("D001") is not None


# -----------------------------------------------------------------------
# End-to-end smoke test
# -----------------------------------------------------------------------

class TestEndToEndSmoke:
    def test_realistic_workspace(self):
        """5 conversations + 1 bot DM filtered + 1 thread walked."""
        tmpdir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir=tmpdir)
        client = MagicMock()
        client.user_id = "U_ME"
        client.list_users.return_value = USERS
        client.list_conversations.return_value = [
            {"id": "D001", "is_im": True, "user": "U001"},
            {"id": "D002", "is_im": True, "user": "BOT"},
            {"id": "G001", "name": "mpdm-me-alice-bob", "is_mpim": True, "is_member": True},
            {"id": "C001", "name": "eng", "is_channel": True, "is_member": True, "is_archived": False},
            {"id": "C002", "name": "secret", "is_group": True, "is_private": True, "is_member": True, "is_archived": False},
            {"id": "C003", "name": "old", "is_channel": True, "is_member": True, "is_archived": True},
        ]

        def fake_fetch(channel_id, **kwargs):
            if channel_id == "C001":
                return [
                    {"user": "U_ME", "ts": "100.0", "text": "thread root", "type": "message",
                     "reply_count": 2, "latest_reply": "200.0"},
                    {"user": "U001", "ts": "300.0", "text": "regular", "type": "message"},
                ]
            return [
                {"user": "U001", "ts": "100.0", "text": f"hi from {channel_id}", "type": "message"},
                {"user": "U_ME", "ts": "150.0", "text": "hey back", "type": "message"},
            ]
        client.fetch_messages.side_effect = fake_fetch

        def fake_thread_replies(channel_id, thread_ts):
            if channel_id == "C001" and thread_ts == "100.0":
                return [
                    {"user": "U_ME", "ts": "100.0", "thread_ts": "100.0"},
                    {"user": "U001", "ts": "150.0", "thread_ts": "100.0"},
                    {"user": "U002", "ts": "200.0", "thread_ts": "100.0"},
                ]
            return []
        client.fetch_thread_replies.side_effect = fake_thread_replies

        result = run_workspace_fetch(client, cache, "50.0", "9999.0", workers=2, show_progress=False)

        assert result["fetched_count"] == 5
        assert result["failed_count"] == 0

        for cid in ["D001", "G001", "C001", "C002", "C003"]:
            assert cache.load(cid) is not None, f"Missing cache for {cid}"
        assert cache.load("D002") is None

        manifest = cache.load_manifest()
        assert len(manifest["conversations"]) == 6
        in_scope_ids = {c["id"] for c in manifest["conversations"] if c["in_scope"]}
        assert in_scope_ids == {"D001", "G001", "C001", "C002", "C003"}
        bot_entry = next(c for c in manifest["conversations"] if c["id"] == "D002")
        assert bot_entry["filter_reason"] == "bot_user"

        c001_cache = cache.load("C001")
        assert "100.0" in c001_cache["threads"]
        assert set(c001_cache["threads"]["100.0"]["participants"]) == {"U_ME", "U001", "U002"}
