from __future__ import annotations


def test_volume_stats_creation():
    from slackwrap.analytics.types import VolumeStats
    vs = VolumeStats(total_messages=1000, you_count=500, them_count=500, you_pct=50.0, them_pct=50.0, per_week=63.0, busiest_day_date="2025-03-14", busiest_day_count=87, active_days=240, total_days=365, weekday_count=800, weekend_count=200, messages_per_active_day=4.2, monthly_volumes={"2025-01": 120}, monthly_rank=[("2025-01", 120, 1)])
    assert vs.total_messages == 1000
    assert vs.active_days == 240


def test_huddle_stats_creation():
    from slackwrap.analytics.types import HuddleStats
    hs = HuddleStats(total_huddles=50, total_seconds=180000, avg_seconds=3600, median_seconds=3000, longest_seconds=7200, shortest_seconds=120, started_by_you=30, started_by_them=20, weekday_breakdown={"Monday": 10}, per_week=2.5, per_month=10.0, huddle_to_message_ratio=30.0)
    assert hs.total_huddles == 50


def test_response_time_stats_creation():
    from slackwrap.analytics.types import ResponseTimeStats
    rts = ResponseTimeStats(your_median=240, your_avg=300, their_median=180, their_avg=250, fastest_hour=10, fastest_hour_median=60, slowest_hour=23, slowest_hour_median=1800, by_hour={10: 60}, monthly_trend={"2025-01": 300})
    assert rts.your_median == 240


def test_streak_stats_creation():
    from slackwrap.analytics.types import StreakStats
    ss = StreakStats(longest_streak_days=47, longest_streak_start=1700000000.0, longest_streak_end=1704000000.0, current_streak_days=12, longest_gap_seconds=1555200, longest_gap_start=1700000000.0, longest_gap_end=1701555200.0, milestones={"1000th message": "2025-03-03"})
    assert ss.longest_streak_days == 47


def test_communication_stats_creation():
    from slackwrap.analytics.types import CommunicationStats
    cs = CommunicationStats(your_avg_words=11.2, their_avg_words=8.7, your_top_words=[("looks", 142)], their_top_words=[("yeah", 203)], your_emoji_total=50, their_emoji_total=30, your_top_emojis=[("rocket", 20)], their_top_emojis=[("thumbsup", 15)], your_reactions_given=100, their_reactions_given=80, top_reactions=[("thumbsup", 50)], your_links=34, their_links=20, your_files=12, their_files=8, message_length_distribution={"short": 400}, emoji_diversity_you=25, emoji_diversity_them=10)
    assert cs.emoji_diversity_you == 25


def test_thread_stats_creation():
    from slackwrap.analytics.types import ThreadStats
    ts = ThreadStats(total_messages=5000, top_level=4000, in_threads=1000, thread_pct=20.0, threads_started_by_you=62, threads_started_by_them=71, deepest_thread=15, avg_thread_depth=3.2)
    assert ts.deepest_thread == 15


def test_trend_stats_creation():
    from slackwrap.analytics.types import TrendStats
    ts = TrendStats(last_30d_count=312, prev_30d_count=263, pct_change_30d=18.6, current_month="2025-04", current_month_count=41, yoy_month="2024-04", yoy_count=35, yoy_pct_change=5.2)
    assert ts.pct_change_30d == 18.6


def test_heatmap_result_creation():
    from slackwrap.analytics.types import HeatmapResult
    hr = HeatmapResult(data={0: {0: 5, 1: 10}}, x_labels=["Mon", "Tue"], y_labels=["00:00", "01:00"])
    assert hr.data[0][1] == 10


def test_relationship_stats_creation():
    from slackwrap.analytics.types import RelationshipStats
    rs = RelationshipStats(reciprocity_index=0.85, conversation_initiations_you=100, conversation_initiations_them=80, first_message={"ts": 1700000000.0, "text": "hello", "user_id": 1}, last_message={"ts": 1710000000.0, "text": "bye", "user_id": 2}, pinned_highlights=[], shared_channel_distribution={"general": 500})
    assert rs.reciprocity_index == 0.85


def test_query_result_creation():
    from slackwrap.analytics.types import QueryResult
    qr = QueryResult(rows=[{"count": 100}], columns=["count"], row_count=1)
    assert qr.row_count == 1
