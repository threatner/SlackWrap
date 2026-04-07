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


class TestThreadBreakdown:
    def test_thread_breakdown(self):
        msgs = [
            {"user": "U_ME", "ts": "1.0", "text": "top level", "subtype": None},
            {"user": "U_ME", "ts": "2.0", "text": "thread parent", "subtype": None, "thread_ts": "2.0", "reply_count": 1},
            {"user": "U001", "ts": "2.5", "text": "reply", "subtype": None, "thread_ts": "2.0"},
            {"user": "U001", "ts": "3.0", "text": "another top", "subtype": None},
        ]
        stats = compute_message_stats(msgs, "U_ME")
        assert stats["top_level_messages"] == 3  # 1.0, 2.0, 3.0
        assert stats["thread_messages"] == 1  # 2.5
        assert stats["threads_started_by_you"] == 1
        assert stats["threads_started_by_them"] == 0


class TestResponseTimeByHour:
    def test_response_time_by_hour(self):
        from datetime import datetime as dt, timezone as tz
        base = dt(2026, 4, 7, 10, 0, tzinfo=tz.utc).timestamp()  # 10 AM UTC
        msgs = []
        for i in range(6):
            # Alternating A and B, 5 min apart, all at ~10 AM UTC
            msgs.append({"user": "A" if i % 2 == 0 else "B", "ts": str(base + i * 300), "text": "msg", "subtype": None})
        stats = compute_message_stats(msgs, "A")
        # Should have data for the local hour equivalent of 10 AM UTC
        expected_hour = dt.fromtimestamp(base, tz=tz.utc).astimezone().hour
        assert expected_hour in stats["response_time_by_hour"]


class TestLinksShared:
    def test_links_shared(self):
        msgs = [
            {"user": "U_ME", "ts": "1.0", "text": "check <https://example.com> and <https://foo.bar>", "subtype": None},
            {"user": "U001", "ts": "2.0", "text": "see <https://test.com>", "subtype": None},
            {"user": "U_ME", "ts": "3.0", "text": "no links here", "subtype": None},
        ]
        stats = compute_message_stats(msgs, "U_ME")
        assert stats["your_links_shared"] == 2
        assert stats["their_links_shared"] == 1

    def test_files_shared(self):
        msgs = [
            {"user": "U_ME", "ts": "1.0", "text": "here", "subtype": None, "files_count": 2, "file_types": ["png", "pdf"]},
            {"user": "U001", "ts": "2.0", "text": "thanks", "subtype": None, "files_count": 1, "file_types": ["jpg"]},
            {"user": "U_ME", "ts": "3.0", "text": "no files", "subtype": None},
        ]
        stats = compute_message_stats(msgs, "U_ME")
        assert stats["your_files_shared"] == 2
        assert stats["their_files_shared"] == 1


class TestFormatMessageReport:
    def test_formats_report(self):
        stats = compute_message_stats(SAMPLE_MESSAGES, "U_ME")
        output = format_message_report(stats, "DM with Alice")
        assert "Message Analytics" in output
        assert "DM with Alice" in output
        assert "Total messages:" in output
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


class TestBusiestDay:
    def test_busiest_day(self):
        from datetime import datetime as dt, timezone as tz
        # 3 messages on day 1, 5 on day 2
        base1 = dt(2026, 4, 6, 10, 0, tzinfo=tz.utc).timestamp()
        base2 = dt(2026, 4, 7, 10, 0, tzinfo=tz.utc).timestamp()
        msgs = []
        for i in range(3):
            msgs.append({"user": "U_ME", "ts": str(base1 + i * 60), "text": "msg", "subtype": None})
        for i in range(5):
            msgs.append({"user": "U_ME", "ts": str(base2 + i * 60), "text": "msg", "subtype": None})
        stats = compute_message_stats(msgs, "U_ME")
        assert stats["busiest_day_count"] == 5
        assert stats["busiest_day_date"] == "2026-04-07"
