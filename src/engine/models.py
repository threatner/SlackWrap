"""
Typed dataclasses for the SlackWrap stats engine.

Phase 1: I/O types (User, UserDirectory, Conversation, HuddleEvent, ThreadParticipation).
Phase 2: Computation types (ConversationStats, MessageBookend, StreakInfo, DayInfo, MonthInfo).
Phase 4 will add WorkspaceStats, PersonInteraction, *Section types.
"""
from dataclasses import dataclass
from datetime import date, datetime
from collections import Counter
from typing import Literal


@dataclass(frozen=True)
class User:
    id: str
    name: str
    is_bot: bool
    is_deleted: bool


@dataclass(frozen=True)
class UserDirectory:
    """Resolves Slack IDs to User records. Built once per run from users.list."""
    users: dict[str, User]
    me_id: str


@dataclass(frozen=True)
class HuddleEvent:
    started_ts: float
    duration_seconds: int
    participants: frozenset[str]
    started_by: str


@dataclass(frozen=True)
class ThreadParticipation:
    """One thread you took part in, used for co-participation aggregation."""
    root_ts: float
    participants: frozenset[str]


@dataclass(frozen=True)
class Conversation:
    """
    Input to the engine. Holds raw messages + metadata for one channel/DM.
    Built from cache in Phase 1; consumed by the engine in Phase 2.
    """
    id: str
    kind: Literal["im", "mpim", "public", "private", "connect"]
    name: str
    is_archived: bool
    member_ids: frozenset[str]
    counterparty_id: str | None
    messages: list[dict]
    huddles: list[HuddleEvent]


# ---------------------------------------------------------------------------
# Phase 2: Computation output types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MessageBookend:
    ts: float
    user_id: str
    conversation_id: str
    conversation_name: str
    text_preview: str


@dataclass(frozen=True)
class StreakInfo:
    length_days: int
    start_date: date
    end_date: date


@dataclass(frozen=True)
class DayInfo:
    date: date
    message_count: int


@dataclass(frozen=True)
class MonthInfo:
    year: int
    month: int
    message_count: int


@dataclass(frozen=True)
class ConversationStats:
    """
    Output of the per-conversation engine. Pure data.
    Consumed by both the per-person formatter AND the workspace aggregator.
    """
    conversation: Conversation
    me_id: str
    window_start: datetime
    window_end: datetime

    # Volume
    message_count_by_user: dict[str, int]
    word_count_by_user: dict[str, int]
    avg_words_by_user: dict[str, float]

    # Time series
    messages_by_day: dict[date, int]
    messages_by_dow: dict[int, int]
    messages_by_hour: dict[int, int]
    messages_by_dow_hour: dict[tuple[int, int], int]

    # Threads
    threads_started_by_user: dict[str, int]
    thread_participations: list[ThreadParticipation]

    # Huddles
    huddle_count: int
    huddle_seconds: int
    huddle_partner_seconds: dict[str, int]

    # Content
    word_freq_by_user: dict[str, Counter]
    emoji_in_text_by_user: dict[str, Counter]
    reactions_given_by_user: dict[str, Counter]
    reactions_received_by_user: dict[str, Counter]
    links_by_user: dict[str, int]
    files_by_user: dict[str, int]

    # Mentions
    mentions_made_by_user: dict[str, Counter]

    # Bookends
    first_message: MessageBookend | None
    last_message: MessageBookend | None
