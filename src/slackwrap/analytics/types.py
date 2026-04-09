from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VolumeStats:
    total_messages: int = 0
    you_count: int = 0
    them_count: int = 0
    you_pct: float = 0.0
    them_pct: float = 0.0
    per_week: float = 0.0
    busiest_day_date: str = ""
    busiest_day_count: int = 0
    active_days: int = 0
    total_days: int = 0
    weekday_count: int = 0
    weekend_count: int = 0
    messages_per_active_day: float = 0.0
    monthly_volumes: dict[str, int] = field(default_factory=dict)
    monthly_rank: list[tuple[str, int, int]] = field(default_factory=list)


@dataclass
class HuddleStats:
    total_huddles: int = 0
    total_seconds: int = 0
    avg_seconds: int = 0
    median_seconds: int = 0
    longest_seconds: int = 0
    shortest_seconds: int = 0
    started_by_you: int = 0
    started_by_them: int = 0
    weekday_breakdown: dict[str, int] = field(default_factory=dict)
    per_week: float = 0.0
    per_month: float = 0.0
    huddle_to_message_ratio: float = 0.0


@dataclass
class ResponseTimeStats:
    your_median: int = 0
    your_avg: int = 0
    their_median: int = 0
    their_avg: int = 0
    fastest_hour: int = 0
    fastest_hour_median: int = 0
    slowest_hour: int = 0
    slowest_hour_median: int = 0
    by_hour: dict[int, int] = field(default_factory=dict)
    monthly_trend: dict[str, int] = field(default_factory=dict)


@dataclass
class StreakStats:
    longest_streak_days: int = 0
    longest_streak_start: float = 0.0
    longest_streak_end: float = 0.0
    current_streak_days: int = 0
    longest_gap_seconds: int = 0
    longest_gap_start: float = 0.0
    longest_gap_end: float = 0.0
    milestones: dict[str, str] = field(default_factory=dict)


@dataclass
class CommunicationStats:
    your_avg_words: float = 0.0
    their_avg_words: float = 0.0
    your_top_words: list[tuple[str, int]] = field(default_factory=list)
    their_top_words: list[tuple[str, int]] = field(default_factory=list)
    your_emoji_total: int = 0
    their_emoji_total: int = 0
    your_top_emojis: list[tuple[str, int]] = field(default_factory=list)
    their_top_emojis: list[tuple[str, int]] = field(default_factory=list)
    your_reactions_given: int = 0
    their_reactions_given: int = 0
    top_reactions: list[tuple[str, int]] = field(default_factory=list)
    your_links: int = 0
    their_links: int = 0
    your_files: int = 0
    their_files: int = 0
    message_length_distribution: dict[str, int] = field(default_factory=dict)
    emoji_diversity_you: int = 0
    emoji_diversity_them: int = 0


@dataclass
class ThreadStats:
    total_messages: int = 0
    top_level: int = 0
    in_threads: int = 0
    thread_pct: float = 0.0
    threads_started_by_you: int = 0
    threads_started_by_them: int = 0
    deepest_thread: int = 0
    avg_thread_depth: float = 0.0


@dataclass
class TrendStats:
    last_30d_count: int = 0
    prev_30d_count: int = 0
    pct_change_30d: float | None = None
    current_month: str = ""
    current_month_count: int = 0
    yoy_month: str = ""
    yoy_count: int | None = None
    yoy_pct_change: float | None = None


@dataclass
class HeatmapResult:
    data: dict[int, dict[int, int]] = field(default_factory=dict)
    x_labels: list[str] = field(default_factory=list)
    y_labels: list[str] = field(default_factory=list)


@dataclass
class RelationshipStats:
    reciprocity_index: float = 0.0
    conversation_initiations_you: int = 0
    conversation_initiations_them: int = 0
    first_message: dict | None = None
    last_message: dict | None = None
    pinned_highlights: list[dict] = field(default_factory=list)
    shared_channel_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class QueryResult:
    rows: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
