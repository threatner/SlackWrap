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
