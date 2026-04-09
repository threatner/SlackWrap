from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class User:
    id: int
    slack_id: str
    name: str | None = None
    display_name: str | None = None
    real_name: str | None = None
    is_bot: bool = False
    timezone: str | None = None
    tz_offset: int | None = None
    title: str | None = None
    start_date: str | None = None
    status_text: str | None = None
    status_emoji: str | None = None
    locale: str | None = None
    avatar_url: str | None = None
    synced_at: float | None = None


@dataclass
class Channel:
    id: int
    slack_id: str
    name: str | None = None
    type: str = "channel"  # 'dm', 'channel', 'group', 'mpim'
    created_at: float | None = None
    topic: str | None = None
    purpose: str | None = None
    num_members: int | None = None
    is_archived: bool = False
    synced_at: float | None = None


@dataclass
class Message:
    id: int
    channel_id: int
    user_id: int | None
    slack_ts: str
    text: str | None = None
    created_at: float = 0.0
    subtype: str | None = None
    thread_ts: str | None = None
    reply_count: int = 0
    files_count: int = 0

    @property
    def is_thread_reply(self) -> bool:
        return self.thread_ts is not None and self.thread_ts != self.slack_ts


@dataclass
class Reaction:
    id: int
    message_id: int
    user_id: int
    emoji_name: str


@dataclass
class Huddle:
    id: int
    channel_id: int
    created_by_user_id: int | None
    started_at: float
    ended_at: float
    participant_ids: list[int] = field(default_factory=list)

    @property
    def duration_seconds(self) -> int:
        return int(self.ended_at - self.started_at)


@dataclass
class File:
    id: int
    channel_id: int | None
    user_id: int | None
    slack_file_id: str
    name: str | None = None
    filetype: str | None = None
    size_bytes: int | None = None
    created_at: float | None = None


@dataclass
class Pin:
    id: int
    channel_id: int
    user_id: int | None
    message_ts: str | None = None
    pinned_at: float | None = None


@dataclass
class Mention:
    id: int
    channel_id: int | None
    from_user_id: int | None
    mentioned_user_id: int | None
    message_ts: str | None = None
    context_text: str | None = None


@dataclass
class SyncState:
    channel_id: int
    last_synced_ts: str | None = None
    last_synced_at: float | None = None
    status: str = "pending"  # 'pending', 'syncing', 'complete', 'error'
