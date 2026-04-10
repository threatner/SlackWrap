from src.main import parse_args
from src.orchestrators.person_flow import build_search_results


class TestBuildSearchResults:
    def test_combines_dm_and_channel_results(self):
        users = [
            {"id": "U001", "real_name": "John Smith"},
            {"id": "U002", "real_name": "Johnny B"},
        ]
        dm_channels = [
            {"id": "D001", "user": "U001"},
            {"id": "D003", "user": "U003"},
        ]
        channels = [
            {"id": "C001", "name": "john-project"},
        ]
        results = build_search_results(users, dm_channels, channels)

        assert len(results) == 2
        assert results[0]["channel_id"] == "D001"
        assert results[0]["label"] == "John Smith (DM)"
        assert results[0]["type"] == "dm"
        assert results[0]["target_user_id"] == "U001"
        assert results[1]["channel_id"] == "C001"
        assert results[1]["label"] == "#john-project (channel)"
        assert results[1]["type"] == "channel"

    def test_skips_users_without_dm(self):
        users = [
            {"id": "U001", "real_name": "John Smith"},
            {"id": "U002", "real_name": "Johnny B"},
        ]
        dm_channels = [
            {"id": "D001", "user": "U001"},
        ]
        channels = []
        results = build_search_results(users, dm_channels, channels)

        assert len(results) == 1
        assert results[0]["label"] == "John Smith (DM)"


class TestParseArgs:
    def test_default_args(self):
        args = parse_args([])
        assert args.no_cache is False
        assert args.clear_cache is False

    def test_no_cache_flag(self):
        args = parse_args(["--no-cache"])
        assert args.no_cache is True

    def test_clear_cache_flag(self):
        args = parse_args(["--clear-cache"])
        assert args.clear_cache is True
