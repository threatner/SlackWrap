from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from slackwrap.slack_client import SlackClient, RateLimiter


class TestRateLimiter:
    def test_allows_requests_under_limit(self):
        limiter = RateLimiter()
        for _ in range(10):
            limiter.acquire("conversations.history")

    def test_tracks_endpoint_counts(self):
        limiter = RateLimiter()
        limiter.acquire("conversations.history")
        limiter.acquire("conversations.history")
        assert limiter.get_count("conversations.history") == 2

    def test_different_endpoints_tracked_separately(self):
        limiter = RateLimiter()
        limiter.acquire("conversations.history")
        limiter.acquire("users.list")
        assert limiter.get_count("conversations.history") == 1
        assert limiter.get_count("users.list") == 1


class TestSlackClient:
    def _mock_response(self, data: dict, status_code: int = 200):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = data
        mock.headers = {}
        mock.raise_for_status = MagicMock()
        return mock

    @patch("slackwrap.slack_client.requests.get")
    def test_auth_test(self, mock_get):
        mock_get.return_value = self._mock_response({
            "ok": True, "user_id": "U12345", "user": "testuser",
            "team": "TestTeam", "team_id": "T12345",
        })
        client = SlackClient(token="xoxp-test-token")
        assert client.user_id == "U12345"
        assert client.username == "testuser"
        assert client.team == "TestTeam"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_messages_single_page(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        history_resp = self._mock_response({
            "ok": True,
            "messages": [
                {"ts": "1700000001.000001", "user": "U1", "text": "hello"},
                {"ts": "1700000002.000001", "user": "U2", "text": "world"},
            ],
            "has_more": False,
        })
        mock_get.side_effect = [auth_resp, history_resp]
        client = SlackClient(token="xoxp-test")
        messages = client.fetch_messages("C12345")
        assert len(messages) == 2
        assert messages[0]["text"] == "hello"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_messages_pagination(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        page1 = self._mock_response({
            "ok": True, "messages": [{"ts": "1.0", "user": "U1", "text": "a"}],
            "has_more": True, "response_metadata": {"next_cursor": "cursor123"},
        })
        page2 = self._mock_response({
            "ok": True, "messages": [{"ts": "2.0", "user": "U1", "text": "b"}],
            "has_more": False,
        })
        mock_get.side_effect = [auth_resp, page1, page2]
        client = SlackClient(token="xoxp-test")
        messages = client.fetch_messages("C12345")
        assert len(messages) == 2

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_user_profile(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        profile_resp = self._mock_response({
            "ok": True, "profile": {
                "display_name": "Alice", "real_name": "Alice Smith", "title": "Engineer",
                "fields": {"Xf123": {"value": "2023-01-15", "label": "Start Date"}},
            },
        })
        mock_get.side_effect = [auth_resp, profile_resp]
        client = SlackClient(token="xoxp-test")
        profile = client.fetch_user_profile("U12345")
        assert profile["display_name"] == "Alice"
        assert profile["title"] == "Engineer"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_pins(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        pins_resp = self._mock_response({
            "ok": True, "items": [
                {"type": "message", "message": {"ts": "1.0"}, "created_by": "U1", "created": 1700000000},
            ],
        })
        mock_get.side_effect = [auth_resp, pins_resp]
        client = SlackClient(token="xoxp-test")
        pins = client.fetch_pins("C12345")
        assert len(pins) == 1
        assert pins[0]["created_by"] == "U1"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_conversation_info(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        info_resp = self._mock_response({
            "ok": True, "channel": {
                "id": "C12345", "name": "general", "created": 1600000000,
                "topic": {"value": "Discussion"}, "purpose": {"value": "General chat"},
                "num_members": 42,
            },
        })
        mock_get.side_effect = [auth_resp, info_resp]
        client = SlackClient(token="xoxp-test")
        info = client.fetch_conversation_info("C12345")
        assert info["name"] == "general"
        assert info["num_members"] == 42

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_team_info(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        team_resp = self._mock_response({
            "ok": True, "team": {
                "id": "T12345", "name": "Acme Corp", "domain": "acme",
                "icon": {"image_68": "https://example.com/icon.png"},
            },
        })
        mock_get.side_effect = [auth_resp, team_resp]
        client = SlackClient(token="xoxp-test")
        info = client.fetch_team_info()
        assert info["name"] == "Acme Corp"

    @patch("slackwrap.slack_client.requests.get")
    def test_fetch_user_conversations(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        convos_resp = self._mock_response({
            "ok": True, "channels": [{"id": "C1", "name": "general"}, {"id": "C2", "name": "random"}],
            "response_metadata": {"next_cursor": ""},
        })
        mock_get.side_effect = [auth_resp, convos_resp]
        client = SlackClient(token="xoxp-test")
        channels = client.fetch_user_conversations("U12345")
        assert len(channels) == 2

    @patch("slackwrap.slack_client.requests.get")
    def test_find_shared_channels_uses_intersection(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        my_convos = self._mock_response({
            "ok": True, "channels": [{"id": "C1"}, {"id": "C2"}, {"id": "C3"}],
            "response_metadata": {"next_cursor": ""},
        })
        their_convos = self._mock_response({
            "ok": True, "channels": [{"id": "C2"}, {"id": "C3"}, {"id": "C4"}],
            "response_metadata": {"next_cursor": ""},
        })
        mock_get.side_effect = [auth_resp, my_convos, their_convos]
        client = SlackClient(token="xoxp-test")
        shared = client.find_shared_channels("U2")
        shared_ids = {ch["id"] for ch in shared}
        assert shared_ids == {"C2", "C3"}

    @patch("slackwrap.slack_client.time.sleep")
    @patch("slackwrap.slack_client.requests.get")
    def test_429_retry_with_retry_after(self, mock_get, mock_sleep):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        rate_limited = self._mock_response({"ok": False, "error": "rate_limited"}, status_code=429)
        rate_limited.headers = {"Retry-After": "1"}
        success_resp = self._mock_response({"ok": True, "messages": [], "has_more": False})
        mock_get.side_effect = [auth_resp, rate_limited, success_resp]
        client = SlackClient(token="xoxp-test")
        messages = client.fetch_messages("C12345")
        assert len(messages) == 0
        mock_sleep.assert_called()

    @patch("slackwrap.slack_client.requests.get")
    def test_slack_api_error_raises_runtime_error(self, mock_get):
        auth_resp = self._mock_response({"ok": True, "user_id": "U1", "user": "test", "team": "T"})
        error_resp = self._mock_response({"ok": False, "error": "channel_not_found"})
        mock_get.side_effect = [auth_resp, error_resp]
        client = SlackClient(token="xoxp-test")
        with pytest.raises(RuntimeError, match="channel_not_found"):
            client.fetch_conversation_info("C999")
