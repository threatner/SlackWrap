from __future__ import annotations

import re
from collections import Counter

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]*)?>")
_LINK_RE = re.compile(r"<https?://[^>]+>")
_EMOJI_RE = re.compile(r":[a-zA-Z0-9_+-]+:")
_EMOJI_EXTRACT_RE = re.compile(r":([a-zA-Z0-9_+-]+):")
_WORD_TOKEN_RE = re.compile(r"[a-zA-Z]{3,}")

# Common English stop words excluded from top-words analysis.
_STOP_WORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "have", "been", "some", "them",
    "than", "its", "over", "also", "that", "other", "into", "more", "this",
    "with", "just", "from", "they", "will", "what", "when", "make", "like",
    "each", "does", "how", "she", "him", "his", "get", "who", "did", "any",
})


def clean_text_for_words(text: str) -> str:
    """Remove Slack markup (code blocks, mentions, links, emoji) for word analysis."""
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _MENTION_RE.sub("", text)
    text = _LINK_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    return text.strip()


def count_words(text: str) -> int:
    """Count words in text after stripping Slack markup."""
    cleaned = clean_text_for_words(text)
    return len(cleaned.split()) if cleaned else 0


def extract_emojis(text: str) -> list[str]:
    """Extract emoji shortcodes from text, ignoring code blocks."""
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    return _EMOJI_EXTRACT_RE.findall(text)


def count_links(text: str) -> int:
    """Count HTTP/HTTPS links in Slack markup."""
    return len(_LINK_RE.findall(text))


def top_words(texts: list[str], n: int = 10) -> list[tuple[str, int]]:
    """Return the *n* most common words (3+ letters) across all texts."""
    counter: Counter[str] = Counter()
    for text in texts:
        cleaned = clean_text_for_words(text)
        words = [w for w in _WORD_TOKEN_RE.findall(cleaned.lower()) if w not in _STOP_WORDS]
        counter.update(words)
    return counter.most_common(n)


def classify_message_length(word_count: int) -> str:
    """Classify a message as short / medium / long by word count."""
    if word_count <= 5:
        return "short"
    if word_count <= 25:
        return "medium"
    return "long"
