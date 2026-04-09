from __future__ import annotations

from collections import Counter

from slackwrap.analytics.filters import Filters, build_where
from slackwrap.analytics.text_processing import (
    clean_text_for_words,
    classify_message_length,
    count_links,
    count_words,
    extract_emojis,
    top_words,
)
from slackwrap.analytics.types import CommunicationStats
from slackwrap.analytics.volume import SYSTEM_SUBTYPES, _system_subtype_clause
from slackwrap.db import Database


def compute_communication(
    db: Database,
    you_id: int,
    them_id: int,
    filters: Filters,
) -> CommunicationStats:
    where, params = build_where(filters)
    base_where = where if where else "WHERE 1=1"
    full_where = f"{base_where} AND {_system_subtype_clause()} AND m.user_id IN (?, ?)"
    full_params = params + list(SYSTEM_SUBTYPES) + [you_id, them_id]

    rows = db.execute(
        f"SELECT m.user_id, m.text, m.id, m.files_count FROM messages m {full_where} ORDER BY m.created_at",
        tuple(full_params),
    ).fetchall()

    if not rows:
        return CommunicationStats()

    # Per-user accumulators
    your_word_counts: list[int] = []
    their_word_counts: list[int] = []
    your_texts: list[str] = []
    their_texts: list[str] = []
    your_emoji_counter: Counter[str] = Counter()
    their_emoji_counter: Counter[str] = Counter()
    your_links = 0
    their_links = 0
    your_files = 0
    their_files = 0
    length_dist: Counter[str] = Counter()

    for row in rows:
        text = row["text"] or ""
        user_id = row["user_id"]
        wc = count_words(text)
        emojis = extract_emojis(text)
        links = count_links(text)
        length_cat = classify_message_length(wc)
        length_dist[length_cat] += 1

        if user_id == you_id:
            your_word_counts.append(wc)
            your_texts.append(text)
            your_emoji_counter.update(emojis)
            your_links += links
            your_files += row["files_count"] or 0
        else:
            their_word_counts.append(wc)
            their_texts.append(text)
            their_emoji_counter.update(emojis)
            their_links += links
            their_files += row["files_count"] or 0

    your_avg_words = sum(your_word_counts) / len(your_word_counts) if your_word_counts else 0.0
    their_avg_words = sum(their_word_counts) / len(their_word_counts) if their_word_counts else 0.0

    # Top words per user
    your_top = top_words(your_texts)
    their_top = top_words(their_texts)

    # Top emojis per user
    your_top_emojis = your_emoji_counter.most_common(10)
    their_top_emojis = their_emoji_counter.most_common(10)

    # Reactions given: count reactions where the reactor is you_id or them_id
    # on messages within the filtered set
    msg_ids = [row["id"] for row in rows]
    your_reactions_given = 0
    their_reactions_given = 0

    if msg_ids:
        placeholders = ", ".join("?" for _ in msg_ids)
        reaction_rows = db.execute(
            f"SELECT r.user_id, r.emoji_name FROM reactions r WHERE r.message_id IN ({placeholders})",
            tuple(msg_ids),
        ).fetchall()

        reaction_counter: Counter[str] = Counter()
        for rr in reaction_rows:
            reaction_counter[rr["emoji_name"]] += 1
            if rr["user_id"] == you_id:
                your_reactions_given += 1
            elif rr["user_id"] == them_id:
                their_reactions_given += 1

        top_reactions = reaction_counter.most_common(10)
    else:
        top_reactions = []

    return CommunicationStats(
        your_avg_words=round(your_avg_words, 1),
        their_avg_words=round(their_avg_words, 1),
        your_top_words=your_top,
        their_top_words=their_top,
        your_emoji_total=sum(your_emoji_counter.values()),
        their_emoji_total=sum(their_emoji_counter.values()),
        your_top_emojis=your_top_emojis,
        their_top_emojis=their_top_emojis,
        your_reactions_given=your_reactions_given,
        their_reactions_given=their_reactions_given,
        top_reactions=top_reactions,
        your_links=your_links,
        their_links=their_links,
        your_files=your_files,
        their_files=their_files,
        message_length_distribution=dict(length_dist),
        emoji_diversity_you=len(your_emoji_counter),
        emoji_diversity_them=len(their_emoji_counter),
    )
