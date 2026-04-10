"""Tests for the workspace aggregator (engine/workspace_stats.py)."""
from collections import Counter
from datetime import date, datetime, timezone

from src.engine.models import (
    Conversation, ConversationStats, HuddleEvent, MessageBookend,
    ThreadParticipation, User, UserDirectory, WorkspaceStats,
)
from src.engine.workspace_stats import aggregate_workspace_stats, _accumulate_people, _compute_interaction_score, _compute_streak


def _user(uid, name, is_bot=False):
    return User(id=uid, name=name, is_bot=is_bot, is_deleted=False)


def _directory():
    return UserDirectory(
        users={
            "U_ME": _user("U_ME", "Me"),
            "U001": _user("U001", "Alice"),
            "U002": _user("U002", "Bob"),
            "U003": _user("U003", "Carol"),
            "BOT": _user("BOT", "GitHub", is_bot=True),
        },
        me_id="U_ME",
    )


def _make_cs(
    conv_id="D001", kind="im", name="Alice", counterparty="U001",
    msg_counts=None, huddles=None, thread_parts=None, threads_started=None,
    emoji=None, reactions_given=None, reactions_received=None,
    word_freq=None, links=None, files=None, mentions=None,
    first_msg=None, last_msg=None, messages_by_day=None,
    messages_by_dow_hour=None, word_count=None,
):
    conv = Conversation(
        id=conv_id, kind=kind, name=name, is_archived=False,
        member_ids=frozenset({"U_ME", counterparty or "U001"}),
        counterparty_id=counterparty if kind == "im" else None,
        messages=[], huddles=huddles or [],
    )
    return ConversationStats(
        conversation=conv, me_id="U_ME",
        window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2026, 12, 31, tzinfo=timezone.utc),
        message_count_by_user=msg_counts or {},
        word_count_by_user=word_count or {},
        avg_words_by_user={},
        messages_by_day=messages_by_day or {},
        messages_by_dow={}, messages_by_hour={},
        messages_by_dow_hour=messages_by_dow_hour or {},
        threads_started_by_user=threads_started or {},
        thread_participations=thread_parts or [],
        huddle_count=len(huddles) if huddles else 0,
        huddle_seconds=sum(h.duration_seconds for h in huddles) if huddles else 0,
        huddle_partner_seconds={},
        word_freq_by_user=word_freq or {},
        emoji_in_text_by_user=emoji or {},
        reactions_given_by_user=reactions_given or {},
        reactions_received_by_user=reactions_received or {},
        links_by_user=links or {},
        files_by_user=files or {},
        mentions_made_by_user=mentions or {},
        first_message=first_msg,
        last_message=last_msg,
    )


class TestAccumulatePeople:
    def test_dm_messages_attributed_to_counterparty(self):
        cs = _make_cs(msg_counts={"U_ME": 50, "U001": 30})
        accs = _accumulate_people([cs], "U_ME")
        assert accs["U001"].dm_messages_exchanged == 80

    def test_group_dm_only_thread_coparticipation(self):
        tp = ThreadParticipation(root_ts=100.0, participants=frozenset({"U_ME", "U001", "U002"}))
        cs = _make_cs(conv_id="G001", kind="mpim", name="group",
                      counterparty=None, msg_counts={"U_ME": 10, "U001": 5},
                      thread_parts=[tp])
        accs = _accumulate_people([cs], "U_ME")
        # Group DM messages do NOT count as dm_messages_exchanged
        assert accs["U001"].dm_messages_exchanged == 0
        assert accs["U001"].thread_coparticipations == 1
        assert accs["U002"].thread_coparticipations == 1

    def test_channel_thread_coparticipation(self):
        tp = ThreadParticipation(root_ts=200.0, participants=frozenset({"U_ME", "U003"}))
        cs = _make_cs(conv_id="C001", kind="public", name="engineering",
                      counterparty=None, thread_parts=[tp])
        accs = _accumulate_people([cs], "U_ME")
        assert accs["U003"].thread_coparticipations == 1
        assert accs["U003"].dm_messages_exchanged == 0

    def test_huddle_seconds_for_1on1(self):
        huddle = HuddleEvent(started_ts=100.0, duration_seconds=600,
                             participants=frozenset({"U_ME", "U001"}), started_by="U_ME")
        cs = _make_cs(huddles=[huddle])
        accs = _accumulate_people([cs], "U_ME")
        assert accs["U001"].huddle_seconds == 600


class TestInteractionScore:
    def test_formula(self):
        from src.engine.workspace_stats import _PersonAcc
        acc = _PersonAcc(dm_messages_exchanged=100, huddle_seconds=3600, thread_coparticipations=10)
        score = _compute_interaction_score(acc)
        assert score == 100 + 60.0 + 20  # 100 + 3600/60 + 10*2


class TestComputeStreak:
    def test_finds_longest_streak(self):
        daily = {
            date(2026, 1, 1): 5, date(2026, 1, 2): 3, date(2026, 1, 3): 7,  # 3 days
            date(2026, 1, 10): 1,  # isolated
            date(2026, 2, 1): 2, date(2026, 2, 2): 4, date(2026, 2, 3): 1,
            date(2026, 2, 4): 3, date(2026, 2, 5): 6,  # 5 days
        }
        streak = _compute_streak(daily)
        assert streak.length_days == 5
        assert streak.start_date == date(2026, 2, 1)
        assert streak.end_date == date(2026, 2, 5)

    def test_empty_returns_none(self):
        assert _compute_streak({}) is None


class TestAggregateWorkspaceStats:
    def test_full_integration(self):
        directory = _directory()

        # DM with Alice: 50+30 messages, 1 huddle
        huddle = HuddleEvent(started_ts=100.0, duration_seconds=1800,
                             participants=frozenset({"U_ME", "U001"}), started_by="U_ME")
        cs1 = _make_cs(
            conv_id="D001", kind="im", name="Alice", counterparty="U001",
            msg_counts={"U_ME": 50, "U001": 30},
            huddles=[huddle],
            messages_by_day={date(2026, 1, 5): 10, date(2026, 1, 6): 20},
            emoji={"U_ME": Counter({"tada": 5})},
            word_freq={"U_ME": Counter({"hello": 10, "world": 5})},
            word_count={"U_ME": 200},
            links={"U_ME": 3},
            files={"U_ME": 1},
            mentions={"U_ME": Counter({"U001": 2}), "U001": Counter({"U_ME": 3})},
            first_msg=MessageBookend(ts=100.0, user_id="U_ME", conversation_id="D001",
                                     conversation_name="Alice", text_preview="first"),
            last_msg=MessageBookend(ts=900.0, user_id="U001", conversation_id="D001",
                                    conversation_name="Alice", text_preview="last"),
        )

        # Channel: thread co-participation with Bob
        tp = ThreadParticipation(root_ts=200.0, participants=frozenset({"U_ME", "U002"}))
        cs2 = _make_cs(
            conv_id="C001", kind="public", name="engineering", counterparty=None,
            msg_counts={"U_ME": 20, "U002": 15},
            thread_parts=[tp],
            messages_by_day={date(2026, 1, 5): 5},
            messages_by_dow_hour={(0, 10): 5},
        )

        ws = aggregate_workspace_stats([cs1, cs2], directory)

        assert isinstance(ws, WorkspaceStats)
        assert ws.me.id == "U_ME"

        # Hero
        assert ws.hero.total_messages_sent == 70  # 50 + 20
        assert ws.hero.total_huddle_seconds == 1800
        assert ws.hero.unique_humans == 2  # Alice (DM + huddle), Bob (thread)
        assert ws.hero.active_conversations == 2

        # People
        assert len(ws.people.top_by_interaction) >= 2
        alice = next(p for p in ws.people.top_by_interaction if p.user.name == "Alice")
        assert alice.dm_messages_exchanged == 80
        assert alice.huddle_seconds == 1800

        bob = next(p for p in ws.people.top_by_interaction if p.user.name == "Bob")
        assert bob.thread_coparticipations == 1

        # Channels
        assert len(ws.channels.top_by_my_messages) == 1
        assert ws.channels.top_by_my_messages[0].name == "engineering"

        # Huddles
        assert ws.huddles.total_huddles == 1
        assert ws.huddles.total_seconds == 1800

        # Messages
        assert ws.messages.top_emojis_in_text[0] == ("tada", 5)
        assert ws.messages.top_words[0] == ("hello", 10)
        assert ws.messages.links_shared == 3
        assert ws.messages.files_shared == 1

        # Mentions
        assert ws.mentions.total_mentions_received == 3  # U001 mentioned U_ME 3 times
        assert ws.mentions.total_mentions_made == 2  # U_ME mentioned U001 2 times
        assert ws.mentions.top_mentioners_of_me[0].user.name == "Alice"

    def test_empty_stats_list(self):
        directory = _directory()
        ws = aggregate_workspace_stats([], directory)
        assert ws.hero.total_messages_sent == 0
        assert ws.hero.unique_humans == 0
        assert ws.people.top_by_interaction == []

    def test_bots_excluded_from_leaderboards(self):
        directory = _directory()
        tp = ThreadParticipation(root_ts=100.0, participants=frozenset({"U_ME", "BOT"}))
        cs = _make_cs(conv_id="C001", kind="public", name="eng",
                      counterparty=None, thread_parts=[tp])
        ws = aggregate_workspace_stats([cs], directory)
        # BOT should not appear in any leaderboard
        for p in ws.people.top_by_interaction:
            assert p.user.name != "GitHub"
