from src.report import format_duration, compute_stats, format_report, extract_huddles


class TestFormatDuration:
    def test_minutes_only(self):
        assert format_duration(900) == "15m"

    def test_hours_and_minutes(self):
        assert format_duration(3900) == "1h 05m"

    def test_zero(self):
        assert format_duration(0) == "0s"

    def test_exact_hour(self):
        assert format_duration(7200) == "2h"

    def test_days_hours_minutes(self):
        assert format_duration(90060) == "1d 1h 01m"

    def test_days_only(self):
        assert format_duration(172800) == "2d"

    def test_seconds_only(self):
        assert format_duration(45) == "45s"


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
        assert stats["median_seconds"] == 1800
        assert stats["started_by_you"] == 1
        assert stats["started_by_them"] == 2

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
        assert stats["median_seconds"] == 0
        assert stats["started_by_you"] == 0

    def test_median_even_count(self):
        huddles = [
            {"room": {"date_start": 1000, "date_end": 2000, "created_by": "U001", "participant_history": ["U_ME", "U001"]}},
            {"room": {"date_start": 3000, "date_end": 6600, "created_by": "U001", "participant_history": ["U_ME", "U001"]}},
        ]
        stats = compute_stats(huddles, "U_ME")
        assert stats["median_seconds"] == (1000 + 3600) // 2


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
        assert "Total huddles:" in output
        assert "Total time:" in output
        assert "Average:" in output
        assert "Median:" in output
        assert "Longest:" in output
        assert "Shortest:" in output
        assert "Per week:" in output
        assert "Per month:" in output
        assert "Who Starts Huddles" in output
        assert "You:" in output
        assert "Them:" in output
        assert "hours" in output.lower()
        assert "By Day of Week" in output

    def test_formats_empty_report(self):
        stats = compute_stats([], "U_ME")

        output = format_report(stats, "DM with Alice", lambda uid: uid)

        assert "No huddles found" in output


class TestExtractHuddles:
    def test_extracts_ended_huddles(self):
        messages = [
            {"user": "U001", "ts": "1.0", "text": "hello", "subtype": None},
            {"user": None, "ts": "2.0", "text": "", "subtype": "huddle_thread", "room": {
                "date_start": 1000, "date_end": 2000, "has_ended": True,
                "participant_history": ["U001", "U002"], "created_by": "U001",
            }},
            {"user": "U002", "ts": "3.0", "text": "bye", "subtype": None},
        ]
        huddles = extract_huddles(messages)
        assert len(huddles) == 1
        assert huddles[0]["room"]["date_start"] == 1000

    def test_skips_ongoing_huddles(self):
        messages = [
            {"user": None, "ts": "1.0", "text": "", "subtype": "huddle_thread", "room": {
                "date_start": 1000, "date_end": 0, "has_ended": False,
                "participant_history": ["U001"], "created_by": "U001",
            }},
        ]
        huddles = extract_huddles(messages)
        assert len(huddles) == 0
