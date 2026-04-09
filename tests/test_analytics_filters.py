from __future__ import annotations
from datetime import date


def test_empty_filters_produce_no_where_clause():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters()
    clause, params = build_where(f)
    assert clause == ""
    assert params == []


def test_single_user_filter():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters(user_id=1)
    clause, params = build_where(f)
    assert "m.user_id = ?" in clause
    assert params == [1]


def test_date_range_filter():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters(date_from=date(2025, 1, 1), date_to=date(2025, 6, 30))
    clause, params = build_where(f)
    assert "m.created_at >= ?" in clause
    assert "m.created_at < ?" in clause
    assert len(params) == 2


def test_channel_filter():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters(channel_id=5)
    clause, params = build_where(f)
    assert "m.channel_id = ?" in clause
    assert params == [5]


def test_combined_filters():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters(user_id=1, channel_id=5, in_thread=True)
    clause, params = build_where(f)
    assert "m.user_id = ?" in clause
    assert "m.channel_id = ?" in clause
    assert "m.thread_ts IS NOT NULL AND m.thread_ts != m.slack_ts" in clause
    assert 1 in params
    assert 5 in params


def test_day_of_week_filter():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters(day_of_week="Monday")
    clause, params = build_where(f)
    assert "strftime('%w'" in clause


def test_hour_filter():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters(hour=14)
    clause, params = build_where(f)
    assert "strftime('%H'" in clause
    assert 14 in params or "14" in params


def test_has_reactions_filter():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters(has_reactions=True)
    clause, params = build_where(f)
    assert "EXISTS" in clause or "reactions" in clause.lower()


def test_relationship_key_filter():
    from slackwrap.analytics.filters import Filters, build_where
    f = Filters(relationship_key="1:2")
    clause, params = build_where(f)
    assert "m.user_id IN" in clause
