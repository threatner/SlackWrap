"""Tests for the pure stats engine (engine/conversation_stats.py)."""
from collections import Counter
from datetime import date, datetime, timezone

from src.engine.models import (
    Conversation, ConversationStats, HuddleEvent, MessageBookend,
    ThreadParticipation, User, UserDirectory,
)
from src.engine.conversation_stats import (
    compute_conversation_stats,
    compute_volume,
    compute_time_series,
    compute_thread_stats,
    compute_huddle_stats,
    compute_word_frequencies,
    compute_emoji_in_text,
    compute_reactions,
    compute_links_files,
    compute_mentions,
    compute_bookends,
    _filter_user_messages,
)


def _make_msg(user, ts, text="hello", subtype=None, **kwargs):
    m = {"user": user, "ts": str(ts), "text": text, "subtype": subtype}
    m.update(kwargs)
    return m


def _make_directory():
    return UserDirectory(
        users={
            "U_ME": User(id="U_ME", name="Me", is_bot=False, is_deleted=False),
            "U001": User(id="U001", name="Alice", is_bot=False, is_deleted=False),
            "U002": User(id="U002", name="Bob", is_bot=False, is_deleted=False),
            "BOT": User(id="BOT", name="GitHub", is_bot=True, is_deleted=False),
        },
        me_id="U_ME",
    )


def _make_conversation(messages, huddles=None, kind="im", counterparty="U001"):
    return Conversation(
        id="D001", kind=kind, name="Alice", is_archived=False,
        member_ids=frozenset({"U_ME", "U001"}),
        counterparty_id=counterparty,
        messages=messages,
        huddles=huddles or [],
    )


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

class TestFilterUserMessages:
    def test_excludes_system_subtypes(self):
        msgs = [
            _make_msg("U_ME", 1.0),
            _make_msg("U_ME", 2.0, subtype="channel_join"),
            _make_msg("U_ME", 3.0, subtype="huddle_thread"),
            _make_msg("U001", 4.0),
        ]
        result = _filter_user_messages(msgs)
        assert len(result) == 2
        assert result[0]["ts"] == "1.0"
        assert result[1]["ts"] == "4.0"

    def test_excludes_slackbot(self):
        msgs = [_make_msg("USLACKBOT", 1.0), _make_msg("U_ME", 2.0)]
        assert len(_filter_user_messages(msgs)) == 1

    def test_excludes_no_user(self):
        msgs = [{"ts": "1.0", "text": "hi", "subtype": None}]
        assert len(_filter_user_messages(msgs)) == 0


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

class TestComputeVolume:
    def test_counts_per_user(self):
        msgs = [
            _make_msg("U_ME", 1.0, "hello world"),
            _make_msg("U_ME", 2.0, "how are you today friend"),
            _make_msg("U001", 3.0, "good thanks"),
        ]
        count, words, avg = compute_volume(msgs)
        assert count == {"U_ME": 2, "U001": 1}
        assert words["U_ME"] == 7  # "hello world" (2) + "how are you today friend" (5)
        assert words["U001"] == 2
        assert avg["U_ME"] == 3.5
        assert avg["U001"] == 2.0

    def test_strips_code_and_links(self):
        msgs = [_make_msg("U_ME", 1.0, "check ```code block``` and <https://example.com|link>")]
        count, words, avg = compute_volume(msgs)
        assert words["U_ME"] == 2  # "check" and "and"


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------

class TestComputeTimeSeries:
    def test_buckets_by_day_dow_hour(self):
        # 2026-01-05 is a Monday, 10:00 UTC
        ts1 = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc).timestamp()
        # 2026-01-06 is a Tuesday, 14:00 UTC
        ts2 = datetime(2026, 1, 6, 14, 0, tzinfo=timezone.utc).timestamp()
        msgs = [_make_msg("U_ME", ts1), _make_msg("U_ME", ts2)]

        by_day, by_dow, by_hour, by_dow_hour = compute_time_series(msgs, None)
        assert date(2026, 1, 5) in by_day
        assert date(2026, 1, 6) in by_day


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------

class TestComputeThreadStats:
    def test_counts_threads_started(self):
        msgs = [
            _make_msg("U_ME", 1.0, reply_count=3),
            _make_msg("U_ME", 2.0, reply_count=0),
            _make_msg("U001", 3.0, reply_count=1),
        ]
        started, _ = compute_thread_stats(msgs, {})
        assert started == {"U_ME": 1, "U001": 1}

    def test_builds_thread_participations(self):
        cached = {
            "100.0": {"participants": ["U_ME", "U001", "U002"], "latest_reply": "200.0"},
        }
        _, participations = compute_thread_stats([], cached)
        assert len(participations) == 1
        assert participations[0].root_ts == 100.0
        assert "U002" in participations[0].participants


# ---------------------------------------------------------------------------
# Huddles
# ---------------------------------------------------------------------------

class TestComputeHuddleStats:
    def test_counts_and_partner_seconds(self):
        huddles = [
            HuddleEvent(started_ts=100.0, duration_seconds=600, participants=frozenset({"U_ME", "U001"}), started_by="U_ME"),
            HuddleEvent(started_ts=200.0, duration_seconds=1200, participants=frozenset({"U_ME", "U001", "U002"}), started_by="U001"),
        ]
        count, total, partners = compute_huddle_stats(huddles, "U_ME")
        assert count == 2
        assert total == 1800
        assert partners["U001"] == 1800  # in both
        assert partners["U002"] == 1200  # in second only


# ---------------------------------------------------------------------------
# Word frequencies
# ---------------------------------------------------------------------------

class TestComputeWordFrequencies:
    def test_extracts_words_per_user(self):
        msgs = [
            _make_msg("U_ME", 1.0, "the quick brown fox"),
            _make_msg("U_ME", 2.0, "the lazy dog fox"),
            _make_msg("U001", 3.0, "hello world there"),
        ]
        freqs = compute_word_frequencies(msgs)
        assert freqs["U_ME"]["fox"] == 2
        assert freqs["U_ME"]["quick"] == 1
        assert freqs["U001"]["hello"] == 1
        # "the" has only 3 chars, so it IS included (regex matches 3+ alpha chars)
        assert freqs["U_ME"]["the"] == 2


# ---------------------------------------------------------------------------
# Emoji
# ---------------------------------------------------------------------------

class TestComputeEmojiInText:
    def test_counts_emojis(self):
        msgs = [
            _make_msg("U_ME", 1.0, "great :tada: :thumbsup:"),
            _make_msg("U001", 2.0, ":fire: :fire:"),
        ]
        emojis = compute_emoji_in_text(msgs)
        assert emojis["U_ME"]["tada"] == 1
        assert emojis["U_ME"]["thumbsup"] == 1
        assert emojis["U001"]["fire"] == 2

    def test_ignores_emoji_in_code_blocks(self):
        msgs = [_make_msg("U_ME", 1.0, "look ```code :tada: block``` nice :fire:")]
        emojis = compute_emoji_in_text(msgs)
        assert emojis["U_ME"]["fire"] == 1
        assert emojis["U_ME"].get("tada", 0) == 0


# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

class TestComputeReactions:
    def test_given_and_received(self):
        msgs = [
            _make_msg("U001", 1.0, reactions=[
                {"name": "thumbsup", "users": ["U_ME"], "count": 1},
                {"name": "fire", "users": ["U_ME", "U002"], "count": 2},
            ]),
            _make_msg("U_ME", 2.0, reactions=[
                {"name": "heart", "users": ["U001"], "count": 1},
            ]),
        ]
        given, received = compute_reactions(msgs)
        # U_ME reacted with thumbsup and fire on U001's message
        assert given["U_ME"]["thumbsup"] == 1
        assert given["U_ME"]["fire"] == 1
        # U001's message received thumbsup, fire
        assert received["U001"]["thumbsup"] == 1
        assert received["U001"]["fire"] == 2
        # U_ME's message received heart from U001
        assert received["U_ME"]["heart"] == 1


# ---------------------------------------------------------------------------
# Links & Files
# ---------------------------------------------------------------------------

class TestComputeLinksFiles:
    def test_counts_links_and_files(self):
        msgs = [
            _make_msg("U_ME", 1.0, "check <https://example.com> and <https://foo.bar|link>", files_count=1),
            _make_msg("U001", 2.0, "no links here", files_count=2),
        ]
        links, files = compute_links_files(msgs)
        assert links["U_ME"] == 2
        assert links["U001"] == 0
        assert files["U_ME"] == 1
        assert files["U001"] == 2


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------

class TestComputeMentions:
    def test_extracts_mentions(self):
        directory = _make_directory()
        msgs = [
            _make_msg("U_ME", 1.0, "hey <@U001> and <@U002>"),
            _make_msg("U001", 2.0, "thanks <@U_ME>"),
        ]
        mentions = compute_mentions(msgs, directory)
        assert mentions["U_ME"]["U001"] == 1
        assert mentions["U_ME"]["U002"] == 1
        assert mentions["U001"]["U_ME"] == 1

    def test_skips_bot_senders(self):
        directory = _make_directory()
        msgs = [_make_msg("BOT", 1.0, "alert <@U_ME>")]
        mentions = compute_mentions(msgs, directory)
        assert "BOT" not in mentions

    def test_skips_self_mentions(self):
        directory = _make_directory()
        msgs = [_make_msg("U_ME", 1.0, "reminder <@U_ME>")]
        mentions = compute_mentions(msgs, directory)
        assert mentions.get("U_ME", Counter()).get("U_ME", 0) == 0

    def test_skips_bot_targets(self):
        directory = _make_directory()
        msgs = [_make_msg("U_ME", 1.0, "hey <@BOT>")]
        mentions = compute_mentions(msgs, directory)
        assert mentions.get("U_ME", Counter()).get("BOT", 0) == 0


# ---------------------------------------------------------------------------
# Bookends
# ---------------------------------------------------------------------------

class TestComputeBookends:
    def test_first_and_last(self):
        conv = _make_conversation([])
        msgs = [
            _make_msg("U_ME", 100.0, "first msg"),
            _make_msg("U001", 200.0, "middle"),
            _make_msg("U_ME", 300.0, "last msg"),
        ]
        first, last = compute_bookends(conv, msgs)
        assert first.ts == 100.0
        assert first.text_preview == "first msg"
        assert last.ts == 300.0
        assert last.text_preview == "last msg"
        assert first.conversation_id == "D001"

    def test_empty_returns_none(self):
        conv = _make_conversation([])
        first, last = compute_bookends(conv, [])
        assert first is None
        assert last is None


# ---------------------------------------------------------------------------
# Top-level integration
# ---------------------------------------------------------------------------

class TestComputeConversationStats:
    def test_full_integration(self):
        ts1 = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc).timestamp()
        ts2 = datetime(2026, 1, 5, 11, 0, tzinfo=timezone.utc).timestamp()
        ts3 = datetime(2026, 1, 6, 9, 0, tzinfo=timezone.utc).timestamp()
        messages = [
            _make_msg("U_ME", ts1, "hello <@U001> world :tada:"),
            _make_msg("U001", ts2, "hey there <@U_ME>", reactions=[
                {"name": "thumbsup", "users": ["U_ME"], "count": 1},
            ]),
            _make_msg("U_ME", ts3, "check <https://example.com>", files_count=1, reply_count=2),
        ]
        huddles = [
            HuddleEvent(started_ts=ts1, duration_seconds=600, participants=frozenset({"U_ME", "U001"}), started_by="U_ME"),
        ]
        conv = _make_conversation(messages, huddles)
        directory = _make_directory()
        cached_threads = {
            str(ts3): {"participants": ["U_ME", "U001", "U002"], "latest_reply": str(ts3 + 100)},
        }

        stats = compute_conversation_stats(
            conv, "U_ME",
            window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 12, 31, tzinfo=timezone.utc),
            user_directory=directory,
            tz=None,
            cached_threads=cached_threads,
        )

        assert isinstance(stats, ConversationStats)
        assert stats.message_count_by_user["U_ME"] == 2
        assert stats.message_count_by_user["U001"] == 1
        assert stats.huddle_count == 1
        assert stats.huddle_seconds == 600
        assert stats.huddle_partner_seconds == {"U001": 600}
        assert stats.links_by_user["U_ME"] == 1
        assert stats.files_by_user["U_ME"] == 1
        assert stats.emoji_in_text_by_user["U_ME"]["tada"] == 1
        assert stats.reactions_given_by_user["U_ME"]["thumbsup"] == 1
        assert stats.mentions_made_by_user["U_ME"]["U001"] == 1
        assert stats.mentions_made_by_user["U001"]["U_ME"] == 1
        assert stats.threads_started_by_user["U_ME"] == 1
        assert len(stats.thread_participations) == 1
        assert stats.first_message is not None
        assert stats.last_message is not None
        assert stats.first_message.ts == ts1
        assert stats.last_message.ts == ts3

    def test_window_filtering(self):
        """Messages outside the window should be excluded."""
        in_window = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc).timestamp()
        out_of_window = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc).timestamp()
        messages = [
            _make_msg("U_ME", in_window, "inside"),
            _make_msg("U_ME", out_of_window, "outside"),
        ]
        conv = _make_conversation(messages)
        directory = _make_directory()

        stats = compute_conversation_stats(
            conv, "U_ME",
            window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 12, 31, tzinfo=timezone.utc),
            user_directory=directory,
        )

        assert stats.message_count_by_user.get("U_ME", 0) == 1

    def test_empty_conversation(self):
        conv = _make_conversation([])
        directory = _make_directory()
        stats = compute_conversation_stats(
            conv, "U_ME",
            window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 12, 31, tzinfo=timezone.utc),
            user_directory=directory,
        )
        assert stats.message_count_by_user == {}
        assert stats.huddle_count == 0
        assert stats.first_message is None
