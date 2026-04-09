"""Chat engine: conversational AI over Slack data with SQL execution."""
from __future__ import annotations

import json
import re

from slackwrap.ai.insights import get_cached_insights
from slackwrap.ai.prompts import build_chat_system_prompt
from slackwrap.ai.sampler import build_stats_summary
from slackwrap.analytics.engine import AnalyticsEngine
from slackwrap.db import Database

_MAX_HISTORY = 20
_SQL_BLOCK_RE = re.compile(r"```sql\s*\n(.*?)\n```", re.DOTALL)
_SAFE_SQL_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


class ChatEngine:
    """Conversational engine backed by Ollama, with SQL execution support."""

    def __init__(
        self,
        db: Database,
        ollama,
        you_id: int,
        them_id: int,
        your_name: str = "You",
        their_name: str = "Them",
    ):
        self.db = db
        self.ollama = ollama
        self.you_id = you_id
        self.them_id = them_id
        self.your_name = your_name
        self.their_name = their_name
        self.history: list[dict] = []

    def ask(self, question: str) -> str:
        """Send a question and return the assistant's response (with SQL results appended)."""
        if not self.ollama.is_available():
            return "Ollama is not available. Please start it with `ollama serve`."

        # Add user message
        self.history.append({"role": "user", "content": question})

        # Build full message list: system + history
        system_prompt = self._get_system_prompt()
        messages = [{"role": "system", "content": system_prompt}] + self.history

        response = self.ollama.chat(messages=messages)

        # Check for SQL blocks and execute them
        response = self._execute_sql_in_response(response)

        # Add assistant message
        self.history.append({"role": "assistant", "content": response})

        # Trim history to cap
        if len(self.history) > _MAX_HISTORY:
            self.history = self.history[-_MAX_HISTORY:]

        return response

    def clear_history(self) -> None:
        """Reset conversation history."""
        self.history = []

    def _get_system_prompt(self) -> str:
        """Build the system prompt with stats summary and cached insights."""
        engine = AnalyticsEngine(self.db)
        stats = build_stats_summary(engine, self.you_id, self.them_id)
        prompt = build_chat_system_prompt(stats, self.your_name, self.their_name)

        # Append cached insights if available
        key = f"{self.you_id}:{self.them_id}"
        cached = get_cached_insights(self.db, relationship_key=key)
        if cached:
            prompt += "\n\nCached AI insights:\n"
            for insight in cached:
                prompt += f"\n--- {insight['insight_type']} ---\n"
                prompt += json.dumps(insight["result"], indent=2, default=str)

        prompt += (
            "\n\nYou may include SQL queries in your response using ```sql blocks. "
            "Only SELECT queries are allowed. The results will be appended automatically."
        )

        return prompt

    def _execute_sql_in_response(self, response: str) -> str:
        """Find ```sql blocks in the response, execute safe SELECTs, append results."""
        matches = _SQL_BLOCK_RE.findall(response)
        if not matches:
            return response

        for sql in matches:
            sql = sql.strip()
            if not _SAFE_SQL_RE.match(sql):
                response += f"\n\n[Skipped non-SELECT query]"
                continue
            try:
                rows = self.db.execute(sql).fetchall()
                if rows:
                    # Format as a compact table
                    columns = list(rows[0].keys())
                    result_lines = [" | ".join(columns)]
                    for row in rows[:50]:  # cap output
                        result_lines.append(" | ".join(str(row[c]) for c in columns))
                    result_text = "\n".join(result_lines)
                    response += f"\n\nQuery result:\n```\n{result_text}\n```"
                else:
                    response += "\n\n[Query returned no results]"
            except Exception as exc:
                response += f"\n\n[SQL error: {exc}]"

        return response
