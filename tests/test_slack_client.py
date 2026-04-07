from unittest.mock import patch, MagicMock
from src.slack_client import SlackClient


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestSearchUsers:
    def test_search_users_filters_by_name(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        users_response = {
            "ok": True,
            "members": [
                {"id": "U001", "name": "john.smith", "real_name": "John Smith", "deleted": False, "is_bot": False},
                {"id": "U002", "name": "jane.doe", "real_name": "Jane Doe", "deleted": False, "is_bot": False},
                {"id": "U003", "name": "johnny.b", "real_name": "Johnny B", "deleted": False, "is_bot": False},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(users_response)):
            results = client.search_users("john")

        assert len(results) == 2
        assert results[0]["id"] == "U001"
        assert results[1]["id"] == "U003"

    def test_search_users_excludes_bots_and_deleted(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        users_response = {
            "ok": True,
            "members": [
                {"id": "U001", "name": "john.smith", "real_name": "John Smith", "deleted": False, "is_bot": False},
                {"id": "U002", "name": "john.bot", "real_name": "John Bot", "deleted": False, "is_bot": True},
                {"id": "U003", "name": "john.gone", "real_name": "John Gone", "deleted": True, "is_bot": False},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(users_response)):
            results = client.search_users("john")

        assert len(results) == 1
        assert results[0]["id"] == "U001"


class TestListDmChannels:
    def test_returns_dm_channels(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        convos_response = {
            "ok": True,
            "channels": [
                {"id": "D001", "user": "U001"},
                {"id": "D002", "user": "U002"},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(convos_response)):
            results = client.list_dm_channels()

        assert len(results) == 2
        assert results[0]["id"] == "D001"
        assert results[0]["user"] == "U001"


class TestSearchChannels:
    def test_search_channels_filters_by_name(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        convos_response = {
            "ok": True,
            "channels": [
                {"id": "C001", "name": "john-project", "is_im": False, "is_mpim": False},
                {"id": "C002", "name": "engineering", "is_im": False, "is_mpim": False},
                {"id": "C003", "name": "john-standup", "is_im": False, "is_mpim": False},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(convos_response)):
            results = client.search_channels("john")

        assert len(results) == 2
        assert results[0]["id"] == "C001"
        assert results[1]["id"] == "C003"


class TestFetchHuddles:
    def test_extracts_huddle_thread_messages(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {"type": "message", "text": "hello"},
                {
                    "type": "message",
                    "subtype": "huddle_thread",
                    "room": {
                        "date_start": 1700000000,
                        "date_end": 1700003600,
                        "has_ended": True,
                        "participant_history": ["U_ME", "U001"],
                        "created_by": "U_ME",
                    },
                },
                {"type": "message", "text": "world"},
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(history_response)):
            huddles = client.fetch_huddles("C12345")

        assert len(huddles) == 1
        assert huddles[0]["room"]["date_start"] == 1700000000

    def test_skips_ongoing_huddles(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "subtype": "huddle_thread",
                    "room": {
                        "date_start": 1700000000,
                        "date_end": 0,
                        "has_ended": False,
                        "participant_history": ["U_ME", "U001"],
                        "created_by": "U_ME",
                    },
                },
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(history_response)):
            huddles = client.fetch_huddles("C12345")

        assert len(huddles) == 0

    def test_paginates_through_history(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        page1 = {
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "subtype": "huddle_thread",
                    "room": {
                        "date_start": 1700000000,
                        "date_end": 1700003600,
                        "has_ended": True,
                        "participant_history": ["U_ME", "U001"],
                        "created_by": "U_ME",
                    },
                },
            ],
            "has_more": True,
            "response_metadata": {"next_cursor": "cursor_abc"},
        }
        page2 = {
            "ok": True,
            "messages": [
                {
                    "type": "message",
                    "subtype": "huddle_thread",
                    "room": {
                        "date_start": 1700010000,
                        "date_end": 1700011800,
                        "has_ended": True,
                        "participant_history": ["U_ME", "U001"],
                        "created_by": "U001",
                    },
                },
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", side_effect=[_mock_response(page1), _mock_response(page2)]):
            huddles = client.fetch_huddles("C12345")

        assert len(huddles) == 2


class TestFetchMessages:
    def test_fetches_all_messages(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {"type": "message", "user": "U001", "ts": "1700000060.000", "text": "world"},
                {"type": "message", "user": "U_ME", "ts": "1700000000.000", "text": "hello"},
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(history_response)):
            messages = client.fetch_messages("C12345")
        assert len(messages) == 2

    def test_fetches_with_oldest_param(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [{"type": "message", "user": "U001", "ts": "1700000120.000", "text": "new"}],
            "has_more": False,
        }
        mock_get = MagicMock(return_value=_mock_response(history_response))
        with patch("src.slack_client.requests.get", mock_get):
            messages = client.fetch_messages("C12345", oldest="1700000060.000")
        call_params = mock_get.call_args[1]["params"]
        assert call_params["oldest"] == "1700000060.000"
        assert len(messages) == 1

    def test_paginates_messages(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        page1 = {
            "ok": True,
            "messages": [{"type": "message", "user": "U001", "ts": "2.0", "text": "b"}],
            "has_more": True, "response_metadata": {"next_cursor": "cursor_abc"},
        }
        page2 = {
            "ok": True,
            "messages": [{"type": "message", "user": "U_ME", "ts": "1.0", "text": "a"}],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", side_effect=[_mock_response(page1), _mock_response(page2)]):
            messages = client.fetch_messages("C12345")
        assert len(messages) == 2


class TestFetchThreadReplies:
    def test_fetches_replies(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        replies_response = {
            "ok": True,
            "messages": [
                {"type": "message", "user": "U001", "ts": "1.0", "text": "parent", "thread_ts": "1.0"},
                {"type": "message", "user": "U_ME", "ts": "1.5", "text": "reply", "thread_ts": "1.0"},
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(replies_response)):
            replies = client.fetch_thread_replies("C12345", "1.0")
        assert len(replies) == 2


class TestFetchMessagesWithThreads:
    def test_includes_thread_replies(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {"type": "message", "user": "U001", "ts": "1.0", "text": "start thread", "reply_count": 1, "thread_ts": "1.0"},
                {"type": "message", "user": "U_ME", "ts": "2.0", "text": "no thread"},
            ],
            "has_more": False,
        }
        replies_response = {
            "ok": True,
            "messages": [
                {"type": "message", "user": "U001", "ts": "1.0", "text": "start thread", "thread_ts": "1.0"},
                {"type": "message", "user": "U_ME", "ts": "1.5", "text": "reply in thread", "thread_ts": "1.0"},
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", side_effect=[
            _mock_response(history_response),
            _mock_response(replies_response),
        ]):
            messages = client.fetch_messages("C12345", include_threads=True)
        # 2 from history + 1 new reply (1.0 is deduped)
        assert len(messages) == 3
        reply_texts = {m["text"] for m in messages}
        assert "reply in thread" in reply_texts

    def test_without_threads_skips_replies(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        history_response = {
            "ok": True,
            "messages": [
                {"type": "message", "user": "U001", "ts": "1.0", "text": "thread parent", "reply_count": 2},
            ],
            "has_more": False,
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(history_response)):
            messages = client.fetch_messages("C12345", include_threads=False)
        assert len(messages) == 1


class TestResolveUserName:
    def test_prefers_display_name(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        user_response = {
            "ok": True,
            "user": {"id": "U001", "real_name": "John Smith", "profile": {"display_name": "Johnny"}},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(user_response)):
            name = client.resolve_user_name("U001")
        assert name == "Johnny"

    def test_falls_back_to_real_name(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        user_response = {
            "ok": True,
            "user": {"id": "U001", "real_name": "John Smith", "profile": {"display_name": ""}},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(user_response)):
            name = client.resolve_user_name("U001")
        assert name == "John Smith"

    def test_caches_results(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        user_response = {
            "ok": True,
            "user": {"id": "U001", "real_name": "John Smith", "profile": {"display_name": ""}},
        }
        mock_get = MagicMock(return_value=_mock_response(user_response))
        with patch("src.slack_client.requests.get", mock_get):
            client.resolve_user_name("U001")
            client.resolve_user_name("U001")
        assert mock_get.call_count == 1

    def test_resolves_own_name_same_as_others(self):
        client = SlackClient(token="xoxp-fake", user_id="U_ME")
        user_response = {
            "ok": True,
            "user": {"id": "U_ME", "real_name": "Rahul Kumar", "profile": {"display_name": "Rahul"}},
        }
        with patch("src.slack_client.requests.get", return_value=_mock_response(user_response)):
            name = client.resolve_user_name("U_ME")
        assert name == "Rahul"
