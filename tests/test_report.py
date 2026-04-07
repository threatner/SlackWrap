from src.report import format_duration, compute_stats


class TestFormatDuration:
    def test_minutes_only(self):
        assert format_duration(900) == "0h 15m"

    def test_hours_and_minutes(self):
        assert format_duration(3900) == "1h 05m"

    def test_zero(self):
        assert format_duration(0) == "0h 00m"

    def test_exact_hour(self):
        assert format_duration(7200) == "2h 00m"


class TestComputeStats:
    def test_computes_aggregate_stats(self):
        huddles = [
            {"room": {"date_start": 1000, "date_end": 2000, "created_by": "U001", "participant_history": ["U_ME", "U001"]}},
            {"room": {"date_start": 3000, "date_end": 6600, "created_by": "U_ME", "participant_history": ["U_ME", "U001"]}},
            {"room": {"date_start": 7000, "date_end": 8800, "created_by": "U001", "participant_history": ["U_ME", "U001"]}},
        ]
        stats = compute_stats(huddles, "U_ME")

        assert stats["total_huddles"] == 3
        assert stats["total_seconds"] == (1000 + 3600 + 1800)
        assert stats["avg_seconds"] == (1000 + 3600 + 1800) // 3
        assert stats["longest_seconds"] == 3600
        assert stats["shortest_seconds"] == 1000

    def test_filters_huddles_without_user(self):
        huddles = [
            {"room": {"date_start": 1000, "date_end": 2000, "created_by": "U001", "participant_history": ["U001", "U002"]}},
            {"room": {"date_start": 3000, "date_end": 6600, "created_by": "U_ME", "participant_history": ["U_ME", "U001"]}},
        ]
        stats = compute_stats(huddles, "U_ME")

        assert stats["total_huddles"] == 1
        assert stats["total_seconds"] == 3600

    def test_empty_huddles(self):
        stats = compute_stats([], "U_ME")
        assert stats["total_huddles"] == 0
        assert stats["total_seconds"] == 0
