from datetime import datetime
from src.message_analytics import compute_message_stats, format_message_report, _clean_text_for_word_count, _build_turns


SAMPLE_MESSAGES = [
    {"user": "U_ME", "ts": "1700000000.000", "text": "hey there how are you", "subtype": None},
    {"user": "U001", "ts": "1700000300.000", "text": "good thanks", "subtype": None},
    {"user": "U_ME", "ts": "1700000600.000", "text": "cool", "subtype": None},
    {"user": "U001", "ts": "1700086700.000", "text": "morning", "subtype": None},
    {"user": "U_ME", "ts": "1700087000.000", "text": "hi good morning how is it going", "subtype": None},
    {"user": None, "ts": "1700087500.000", "text": "", "subtype": "huddle_thread", "room": {}},
    {"user": "USLACKBOT", "ts": "1700088000.000", "text": "joined", "subtype": "channel_join"},
]


class TestCleanTextForWordCount:
    def test_strips_code_blocks(self):
        text = "check this ```\ndef foo():\n    pass\n```"
        assert _clean_text_for_word_count(text) == "check this"

    def test_strips_inline_code(self):
        text = "use `foo()` to do it"
        assert _clean_text_for_word_count(text) == "use  to do it"

    def test_strips_mentions(self):
        text = "hey <@U12345> check this"
        assert _clean_text_for_word_count(text) == "hey  check this"

    def test_strips_links(self):
        text = "see <https://example.com/long/path|example.com> for details"
        assert _clean_text_for_word_count(text) == "see  for details"

    def test_strips_emoji(self):
        text = "sounds good :thumbsup: :rocket:"
        assert _clean_text_for_word_count(text) == "sounds good"

    def test_plain_text_unchanged(self):
        text = "hello how are you"
        assert _clean_text_for_word_count(text) == "hello how are you"

    def test_only_emoji_returns_empty(self):
        text = ":thumbsup:"
        assert _clean_text_for_word_count(text) == ""


class TestBuildTurns:
    def test_collapses_consecutive_same_user(self):
        msgs = [
            {"user": "A", "ts": "1.0"},
            {"user": "A", "ts": "2.0"},
            {"user": "A", "ts": "3.0"},
            {"user": "B", "ts": "4.0"},
        ]
        turns = _build_turns(msgs)
        assert len(turns) == 2
        assert turns[0]["user"] == "A"
        assert turns[0]["start_ts"] == 1.0
        assert turns[0]["end_ts"] == 3.0
        assert turns[0]["count"] == 3
        assert turns[1]["user"] == "B"
        assert turns[1]["count"] == 1

    def test_alternating_users(self):
        msgs = [
            {"user": "A", "ts": "1.0"},
            {"user": "B", "ts": "2.0"},
            {"user": "A", "ts": "3.0"},
        ]
        turns = _build_turns(msgs)
        assert len(turns) == 3

    def test_empty(self):
        assert _build_turns([]) == []


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
        # "hey there how are you" = 5, "cool" = 1, "hi good morning how is it going" = 7 -> avg 4.3
        # "good thanks" = 2, "morning" = 1 -> avg 1.5
        assert stats["your_avg_words"] == 4.3
        assert stats["their_avg_words"] == 1.5

    def test_word_count_ignores_code_blocks(self):
        msgs = [
            {"user": "U_ME", "ts": "1.0", "text": "here ```\ndef foo():\n    bar()\n    baz()\n``` done", "subtype": None},
        ]
        stats = compute_message_stats(msgs, "U_ME")
        # "here" + "done" = 2 words, code block stripped
        assert stats["your_avg_words"] == 2.0

    def test_initiations(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert stats["you_initiated"] == 1
        assert stats["them_initiated"] == 1

    def test_response_time_turn_based(self):
        # A sends at t=0, A sends at t=300, B replies at t=360
        # Turn-based: turn A starts at t=0, turn B starts at t=360
        # B's response time = 360 - 0 = 360s (not 60s from last msg)
        msgs = [
            {"user": "A", "ts": "0.0", "text": "hey", "subtype": None},
            {"user": "A", "ts": "300.0", "text": "you there?", "subtype": None},
            {"user": "B", "ts": "360.0", "text": "yeah", "subtype": None},
        ]
        stats = compute_message_stats(msgs, "A")
        assert stats["their_avg_response_seconds"] == 360
        assert stats["their_median_response_seconds"] == 360

    def test_response_time_has_median(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert "your_median_response_seconds" in stats
        assert "their_median_response_seconds" in stats

    def test_empty_messages(self):
        stats = compute_message_stats([], "U_ME")
        assert stats["total_messages"] == 0
        assert stats["you_count"] == 0
        assert stats["your_median_response_seconds"] == 0

    def test_weekday_breakdown(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert isinstance(stats["weekday_breakdown"], dict)
        assert sum(stats["weekday_breakdown"].values()) == 5

    def test_hourly_breakdown(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        assert isinstance(stats["hourly_breakdown"], dict)
        assert sum(stats["hourly_breakdown"].values()) == 5


class TestTrendAnalysis:
    def test_trend_30d(self):
        from datetime import date, timedelta, timezone as tz
        now = date.today()
        msgs = []
        for i in range(10):
            d = now - timedelta(days=i+1)
            ts = datetime(d.year, d.month, d.day, tzinfo=tz.utc).timestamp()
            msgs.append({"user": "U_ME", "ts": str(ts), "text": "recent", "subtype": None})
        for i in range(5):
            d = now - timedelta(days=35+i)
            ts = datetime(d.year, d.month, d.day, tzinfo=tz.utc).timestamp()
            msgs.append({"user": "U_ME", "ts": str(ts), "text": "older", "subtype": None})
        stats = compute_message_stats(msgs, "U_ME")
        assert stats["trend_last_30d_count"] == 10
        assert stats["trend_prev_30d_count"] == 5
        assert stats["trend_30d_pct_change"] == 100.0


class TestFormatMessageReport:
    def test_formats_report(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "Message Analytics" in output
        assert "DM with Alice" in output
        assert "Total messages:" in output
        assert "Who Initiates" in output
        assert "Response Time" in output
        assert "median" in output
        assert "avg" in output
        assert "Message Style" in output
        assert "Most Active Hours" in output
        assert "By Day of Week" in output

    def test_formats_empty_report(self):
        stats = compute_message_stats([], "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "No messages found" in output
