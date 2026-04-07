from src.report import format_duration, compute_stats, format_report


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


class TestFormatReport:
    def test_formats_report_with_huddles(self):
        huddles = [
            {"room": {"date_start": 1700000000, "date_end": 1700001920, "created_by": "U001", "participant_history": ["U_ME", "U001"]}},
            {"room": {"date_start": 1700100000, "date_end": 1700103600, "created_by": "U_ME", "participant_history": ["U_ME", "U001"]}},
        ]
        stats = compute_stats(huddles, "U_ME")

        def mock_resolve(uid):
            return {"U_ME": "You", "U001": "Alice"}.get(uid, uid)

        output = format_report(stats, "DM with Alice", mock_resolve)

        assert "Huddle Time Report" in output
        assert "DM with Alice" in output
        assert "Total huddles: 2" in output
        assert "Alice" in output
        assert "You" in output
        assert "Total time:" in output
        assert "Avg per huddle:" in output
        assert "Longest huddle:" in output
        assert "Shortest huddle:" in output

    def test_formats_empty_report(self):
        stats = compute_stats([], "U_ME")

        output = format_report(stats, "DM with Alice", lambda uid: uid)

        assert "No huddles found" in output
