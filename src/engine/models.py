"""
Typed dataclasses for the SlackWrap stats engine.

Phase 1: I/O-relevant types (User, UserDirectory, Conversation, HuddleEvent, ThreadParticipation).
Phase 2 will add ConversationStats, MessageBookend, StreakInfo, etc.
Phase 4 will add WorkspaceStats, PersonInteraction, *Section types.
"""
from dataclasses import dataclass
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
