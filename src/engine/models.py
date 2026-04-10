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


# ---------------------------------------------------------------------------
# Phase 4: Workspace aggregation types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PersonInteraction:
    user: User
    dm_messages_exchanged: int
    huddle_seconds: int
    thread_coparticipations: int
    interaction_score: float
    last_seen_ts: float


@dataclass(frozen=True)
class ChannelRanking:
    conversation_id: str
    name: str
    kind: str
    my_message_count: int
    total_message_count: int


@dataclass(frozen=True)
class MentionCount:
    user: User
    count: int


@dataclass(frozen=True)
class ChannelMentionCount:
    conversation_id: str
    name: str
    count: int


@dataclass(frozen=True)
class HeroStats:
    total_messages_sent: int
    total_huddle_seconds: int
    unique_humans: int
    active_conversations: int
    longest_streak: StreakInfo | None
    busiest_day: DayInfo | None


@dataclass(frozen=True)
class PeopleSection:
    top_by_interaction: list[PersonInteraction]
    top_by_dm_volume: list[PersonInteraction]
    top_by_huddle_time: list[PersonInteraction]
    top_by_thread_coparticipation: list[PersonInteraction]
    rediscovery: list[PersonInteraction]
    new_people: list[User]
    lost_people: list[User]


@dataclass(frozen=True)
class ChannelsSection:
    top_by_my_messages: list[ChannelRanking]
    top_by_total_volume: list[ChannelRanking]
    lurker_channels: list[ChannelRanking]
    count_by_type: dict[str, int]


@dataclass(frozen=True)
class HuddlesSection:
    total_huddles: int
    total_seconds: int
    avg_seconds: float
    partner_leaderboard: list[PersonInteraction]
    longest_huddle_seconds: int
    longest_huddle_partner: User | None


@dataclass(frozen=True)
class MessagesSection:
    daily_volume_timeline: list[tuple[date, int]]
    dow_hour_heatmap: dict[tuple[int, int], int]
    top_emojis_in_text: list[tuple[str, int]]
    top_reactions_given: list[tuple[str, int]]
    top_reactions_received: list[tuple[str, int]]
    top_words: list[tuple[str, int]]
    avg_words_per_message: float
    threads_started: int
    threads_replied_in: int
    links_shared: int
    files_shared: int
    first_message: MessageBookend | None
    last_message: MessageBookend | None


@dataclass(frozen=True)
class MentionsSection:
    total_mentions_received: int
    top_mentioners_of_me: list[MentionCount]
    total_mentions_made: int
    top_people_i_mentioned: list[MentionCount]
    top_channels_where_mentioned: list[ChannelMentionCount]


@dataclass(frozen=True)
class TrendsSection:
    message_volume_change_pct: float | None
    huddle_time_change_pct: float | None
    unique_people_change: int
    most_active_month: MonthInfo | None
    quietest_month: MonthInfo | None


@dataclass(frozen=True)
class WorkspaceStats:
    me: User
    window_start: datetime
    window_end: datetime
    hero: HeroStats
    people: PeopleSection
    channels: ChannelsSection
    huddles: HuddlesSection
    messages: MessagesSection
    mentions: MentionsSection
    trends: TrendsSection
    failed_conversations: list[tuple[str, str]]
