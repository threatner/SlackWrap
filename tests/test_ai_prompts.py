from __future__ import annotations


def test_tone_prompt_includes_messages():
    from slackwrap.ai.prompts import build_tone_prompt
    messages = [{"text": "hey how are you", "created_at": 1700000000.0}]
    prompt = build_tone_prompt(messages, month="2023-11")
    assert "2023-11" in prompt and "hey how are you" in prompt


def test_fun_facts_prompt_includes_stats():
    from slackwrap.ai.prompts import build_fun_facts_prompt
    stats = {"total_messages": 5000, "active_days": 240, "longest_streak": 47}
    prompt = build_fun_facts_prompt(stats)
    assert "5000" in prompt or "5,000" in prompt


def test_chat_system_prompt_includes_names():
    from slackwrap.ai.prompts import build_chat_system_prompt
    prompt = build_chat_system_prompt(stats_summary={"total_messages": 1000},
                                      your_name="Alice", their_name="Bob")
    assert "Alice" in prompt and "Bob" in prompt


def test_style_prompt_includes_stats():
    from slackwrap.ai.prompts import build_style_prompt
    stats = {"your_avg_words": 11.2, "their_avg_words": 8.7, "your_emoji_total": 50}
    prompt = build_style_prompt(stats, your_name="Alice", their_name="Bob")
    assert "Alice" in prompt and "11.2" in prompt


def test_sql_generation_prompt():
    from slackwrap.ai.prompts import build_sql_prompt
    prompt = build_sql_prompt(question="How many messages in January?",
                              schema_description="messages(id, text, created_at)")
    assert "January" in prompt and "messages" in prompt
