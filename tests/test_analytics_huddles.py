from __future__ import annotations
import json
import pytest
from slackwrap.analytics.filters import Filters

@pytest.fixture
def seeded_huddles(db):
    u1 = db.upsert_user(slack_id="U1", name="alice")
    u2 = db.upsert_user(slack_id="U2", name="bob")
    ch = db.upsert_channel(slack_id="C1", name="dm", type="dm")
    db.commit()
    huddles = [
        (ch, u1, 1700049600.0, 1700053200.0, 3600, json.dumps(["U1", "U2"])),   # Mon 14:00
        (ch, u2, 1700136000.0, 1700137800.0, 1800, json.dumps(["U1", "U2"])),   # Tue 14:00
        (ch, u1, 1700222400.0, 1700229600.0, 7200, json.dumps(["U1", "U2"])),   # Wed 14:00
        (ch, u1, 1700308800.0, 1700308920.0, 120, json.dumps(["U1", "U2"])),    # Thu 14:00
        (ch, u2, 1700395200.0, 1700398800.0, 3600, json.dumps(["U1", "U2"])),   # Fri 14:00
    ]
    for channel_id, created_by, start, end, dur, participants in huddles:
        db.execute(
            "INSERT INTO huddles (channel_id, created_by_user_id, started_at, ended_at, duration_seconds, participant_ids) VALUES (?, ?, ?, ?, ?, ?)",
            (channel_id, created_by, start, end, dur, participants))
    db.commit()
    return db, u1, u2, ch

def test_huddle_total_count(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles
    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_huddles == 5

def test_huddle_total_time(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles
    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.total_seconds == 16320

def test_huddle_who_starts(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles
    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.started_by_you == 3
    assert stats.started_by_them == 2

def test_huddle_longest_shortest(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles
    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.longest_seconds == 7200
    assert stats.shortest_seconds == 120

def test_huddle_median(seeded_huddles):
    from slackwrap.analytics.huddles import compute_huddles
    db, u1, u2, ch = seeded_huddles
    stats = compute_huddles(db, you_id=u1, them_id=u2, filters=Filters(channel_id=ch))
    assert stats.median_seconds == 3600
