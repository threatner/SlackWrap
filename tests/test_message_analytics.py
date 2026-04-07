from src.message_analytics import compute_message_stats, format_message_report


SAMPLE_MESSAGES = [
    {"user": "U_ME", "ts": "1700000000.000", "text": "hey there how are you", "subtype": None},
    {"user": "U001", "ts": "1700000300.000", "text": "good thanks", "subtype": None},
    {"user": "U_ME", "ts": "1700000600.000", "text": "cool", "subtype": None},
    {"user": "U001", "ts": "1700086700.000", "text": "morning", "subtype": None},
    {"user": "U_ME", "ts": "1700087000.000", "text": "hi good morning how is it going", "subtype": None},
    {"user": None, "ts": "1700087500.000", "text": "", "subtype": "huddle_thread", "room": {}},
    {"user": "USLACKBOT", "ts": "1700088000.000", "text": "joined", "subtype": "channel_join"},
]


class TestComputeMessageStats:
    def test_counts_messages(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["total_messages"] == 5
        assert stats["you_count"] == 3
        assert stats["them_count"] == 2

    def test_excludes_system_messages(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["total_messages"] == 5

    def test_percentages(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["you_pct"] == 60.0
        assert stats["them_pct"] == 40.0

    def test_avg_word_count(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["your_avg_words"] == 4.3
        assert stats["their_avg_words"] == 1.5

    def test_initiations(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["you_initiated"] == 1
        assert stats["them_initiated"] == 1

    def test_response_times(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["your_avg_response_seconds"] > 0
        assert stats["their_avg_response_seconds"] > 0

    def test_empty_messages(self):
        stats = compute_message_stats([], "U_ME")
        assert stats["total_messages"] == 0
        assert stats["you_count"] == 0

    def test_weekday_breakdown(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert isinstance(stats["weekday_breakdown"], dict)
        assert sum(stats["weekday_breakdown"].values()) == 5

    def test_hourly_breakdown(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert isinstance(stats["hourly_breakdown"], dict)
        assert sum(stats["hourly_breakdown"].values()) == 5


class TestFormatMessageReport:
    def test_formats_report(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "Message Analytics" in output
        assert "DM with Alice" in output
        assert "Total messages:" in output
        assert "You" in output
        assert "Them:" in output
        assert "Who Initiates" in output
        assert "Response Time" in output
        assert "Message Style" in output
        assert "Most Active Hours" in output
        assert "By Day of Week" in output

    def test_formats_empty_report(self):
        stats = compute_message_stats([], "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "No messages found" in output
