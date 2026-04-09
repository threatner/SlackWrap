from __future__ import annotations

import json
from datetime import datetime, timezone


def _format_message(msg: dict) -> str:
    """Format a single message dict for inclusion in a prompt."""
    ts = msg.get("created_at", 0.0)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    text = msg.get("text", "")
    return f"[{dt}] {text}"


def build_tone_prompt(messages: list[dict], month: str) -> str:
    """Build a prompt for tone/sentiment analysis of messages in a given month."""
    formatted = "\n".join(_format_message(m) for m in messages)
    return f"""Analyze the tone and sentiment of the following Slack messages from {month}.

Messages:
{formatted}

Respond with a JSON object containing:
- "tone": primary tone label (e.g. "friendly", "professional", "casual", "enthusiastic", "neutral")
- "sentiment": overall sentiment score from -1.0 (very negative) to 1.0 (very positive)
- "confidence": confidence in your assessment from 0.0 to 1.0
- "keywords": list of up to 5 words that characterize the tone
- "summary": one-sentence description of the communication tone"""


def build_style_prompt(stats: dict, your_name: str, their_name: str) -> str:
    """Build a prompt for analyzing communication style differences."""
    stats_text = json.dumps(stats, indent=2, default=str)
    return f"""Analyze the communication style between {your_name} and {their_name} based on these statistics:

{stats_text}

Respond with a JSON object containing:
- "your_style": a 1-2 sentence description of {your_name}'s communication style
- "their_style": a 1-2 sentence description of {their_name}'s communication style
- "compatibility": a score from 0.0 to 1.0 indicating communication compatibility
- "dynamics": a 1-2 sentence description of the conversation dynamics
- "fun_observation": one fun or surprising observation about their styles"""


def build_fun_facts_prompt(stats: dict) -> str:
    """Build a prompt for generating fun facts from conversation statistics."""
    stats_text = json.dumps(stats, indent=2, default=str)
    return f"""Generate fun and interesting facts about this Slack conversation based on these statistics:

{stats_text}

Respond with a JSON object containing:
- "facts": a list of 5-7 fun facts, each as a string. Make them specific, surprising, and conversational.
  Use the actual numbers from the stats. Compare to relatable things (e.g. "That's enough messages to fill X books").
- "superlative": the single most impressive or surprising stat, as a one-liner
- "headline": a catchy headline summarizing the relationship in 5-8 words"""


def build_trajectory_prompt(monthly_stats: list[dict], your_name: str, their_name: str) -> str:
    """Build a prompt for analyzing conversation trajectory over time."""
    stats_text = json.dumps(monthly_stats, indent=2, default=str)
    return f"""Analyze the trajectory of the conversation between {your_name} and {their_name} over time.

Monthly data (chronological):
{stats_text}

Respond with a JSON object containing:
- "phases": list of objects, each with "period" (date range), "label" (e.g. "Getting Started", "Peak Activity"), and "description" (1 sentence)
- "trend": overall trend ("growing", "stable", "declining", "cyclical")
- "turning_points": list of months where significant changes occurred, with brief explanations
- "prediction": one-sentence prediction about the future trajectory
- "story": a 2-3 sentence narrative arc of the relationship"""


def build_chat_system_prompt(
    stats_summary: dict,
    your_name: str,
    their_name: str,
) -> str:
    """Build a system prompt for the conversational chat interface."""
    stats_text = json.dumps(stats_summary, indent=2, default=str)
    return f"""You are SlackWrap, an AI assistant that helps {your_name} explore their Slack conversation history with {their_name}.

You have access to detailed statistics about their messaging relationship:
{stats_text}

Guidelines:
- Answer questions about their conversation patterns, statistics, and history
- Be conversational, warm, and occasionally witty
- Reference specific numbers and data points when relevant
- If asked something you cannot determine from the available data, say so honestly
- Keep responses concise (2-4 sentences) unless asked for detail
- You can suggest interesting follow-up questions based on the data
- Respect privacy: focus on patterns and aggregates rather than specific message content"""


def build_sql_prompt(question: str, schema_description: str) -> str:
    """Build a prompt for generating SQL queries from natural language questions."""
    return f"""Generate a SQLite query to answer the following question about Slack message data.

Database schema:
{schema_description}

Question: {question}

Respond with a JSON object containing:
- "sql": the SQL query string (SELECT only, no modifications)
- "explanation": brief explanation of what the query does
- "columns": list of column names the query will return
- "warning": any caveats about the query results (or null if none)

Important:
- Only generate SELECT statements, never INSERT/UPDATE/DELETE/DROP
- Use strftime for date operations (SQLite)
- Timestamps are stored as Unix epoch floats in created_at columns
- Use date(created_at, 'unixepoch') for date conversions"""
