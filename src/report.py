from datetime import datetime, timezone
from typing import Callable


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes:02d}m"


def compute_stats(huddles: list[dict], user_id: str) -> dict:
    user_huddles = [
        h for h in huddles
        if user_id in h["room"]["participant_history"]
    ]
    if not user_huddles:
        return {
            "total_huddles": 0,
            "total_seconds": 0,
            "avg_seconds": 0,
            "longest_seconds": 0,
            "shortest_seconds": 0,
            "huddles": [],
        }
    durations = [
        h["room"]["date_end"] - h["room"]["date_start"]
        for h in user_huddles
    ]
    return {
        "total_huddles": len(user_huddles),
        "total_seconds": sum(durations),
        "avg_seconds": sum(durations) // len(durations),
        "longest_seconds": max(durations),
        "shortest_seconds": min(durations),
        "huddles": user_huddles,
    }
