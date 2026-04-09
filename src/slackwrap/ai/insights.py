"""Batch insight generation with caching for fun facts, style, and trajectory."""
from __future__ import annotations

import hashlib
import json
import time

from slackwrap.ai.prompts import (
    build_fun_facts_prompt,
    build_style_prompt,
    build_trajectory_prompt,
)
from slackwrap.ai.sampler import build_stats_summary
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.db import Database


def _hash_input(data: str) -> str:
    """Create a stable hash for cache-keying prompt inputs."""
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _is_cached(db: Database, relationship_key: str, insight_type: str, input_hash: str) -> bool:
    """Check whether an insight with this hash already exists."""
    row = db.execute(
        "SELECT id FROM ai_insights WHERE relationship_key = ? AND insight_type = ? AND input_hash = ?",
        (relationship_key, insight_type, input_hash),
    ).fetchone()
    return row is not None


def _store_insight(
    db: Database,
    relationship_key: str,
    insight_type: str,
    model_name: str,
    input_hash: str,
    result: dict,
) -> None:
    """Persist an insight row to the database."""
    db.execute(
        "INSERT INTO ai_insights (relationship_key, insight_type, model_name, input_hash, result_json, generated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (relationship_key, insight_type, model_name, input_hash, json.dumps(result), time.time()),
    )
    db.commit()


def generate_insights(
    db: Database,
    ollama,
    you_id: int,
    them_id: int,
    relationship_key: str,
    your_name: str,
    their_name: str,
) -> None:
    """Generate fun_facts, style, and trajectory insights, skipping any already cached."""
    if not ollama.is_available():
        return

    engine = AnalyticsEngine(db)
    stats = build_stats_summary(engine, you_id, them_id)
    stats_json = json.dumps(stats, sort_keys=True, default=str)

    # --- fun_facts ---
    ff_hash = _hash_input(f"fun_facts:{stats_json}")
    if not _is_cached(db, relationship_key, "fun_facts", ff_hash):
        prompt = build_fun_facts_prompt(stats)
        schema = {
            "type": "object",
            "properties": {
                "facts": {"type": "array", "items": {"type": "string"}},
                "superlative": {"type": "string"},
                "headline": {"type": "string"},
            },
            "required": ["facts"],
        }
        result = ollama.chat_json(
            messages=[{"role": "user", "content": prompt}],
            schema=schema,
        )
        _store_insight(db, relationship_key, "fun_facts", ollama.chat_model, ff_hash, result)

    # --- style ---
    style_hash = _hash_input(f"style:{stats_json}")
    if not _is_cached(db, relationship_key, "style", style_hash):
        prompt = build_style_prompt(stats, your_name, their_name)
        schema = {
            "type": "object",
            "properties": {
                "your_style": {"type": "string"},
                "their_style": {"type": "string"},
                "compatibility": {"type": "number"},
                "dynamics": {"type": "string"},
                "fun_observation": {"type": "string"},
            },
            "required": ["your_style", "their_style"],
        }
        result = ollama.chat_json(
            messages=[{"role": "user", "content": prompt}],
            schema=schema,
        )
        _store_insight(db, relationship_key, "style", ollama.chat_model, style_hash, result)

    # --- trajectory ---
    traj_hash = _hash_input(f"trajectory:{stats_json}")
    if not _is_cached(db, relationship_key, "trajectory", traj_hash):
        # Build minimal monthly stats for the trajectory prompt
        monthly: list[dict] = []
        try:
            rollups = engine.rollups(you_id, them_id)
            for r in rollups:
                monthly.append({
                    "month": r.month,
                    "total_messages": r.total_messages,
                    "you_count": r.you_count,
                    "them_count": r.them_count,
                })
        except Exception:
            monthly = [{"month": "overall", "total_messages": stats.get("total_messages", 0)}]

        prompt = build_trajectory_prompt(monthly, your_name, their_name)
        schema = {
            "type": "object",
            "properties": {
                "phases": {"type": "array", "items": {"type": "object"}},
                "trend": {"type": "string"},
                "turning_points": {"type": "array", "items": {"type": "string"}},
                "prediction": {"type": "string"},
                "story": {"type": "string"},
            },
            "required": ["trend", "story"],
        }
        result = ollama.chat_json(
            messages=[{"role": "user", "content": prompt}],
            schema=schema,
        )
        _store_insight(db, relationship_key, "trajectory", ollama.chat_model, traj_hash, result)


def get_cached_insights(db: Database, relationship_key: str) -> list[dict]:
    """Return all cached insights for a relationship as a list of dicts."""
    rows = db.execute(
        "SELECT id, relationship_key, insight_type, model_name, input_hash, result_json, generated_at "
        "FROM ai_insights WHERE relationship_key = ? ORDER BY generated_at",
        (relationship_key,),
    ).fetchall()
    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "relationship_key": row["relationship_key"],
            "insight_type": row["insight_type"],
            "model_name": row["model_name"],
            "input_hash": row["input_hash"],
            "result": json.loads(row["result_json"]),
            "generated_at": row["generated_at"],
        })
    return results
