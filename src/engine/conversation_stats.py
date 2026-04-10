"""
Pure per-conversation stats engine.

compute_conversation_stats(conversation, me_id, window_start, window_end,
                           user_directory, tz, cached_threads) -> ConversationStats

All functions are pure: no I/O, no formatting, no printing.
Logic lifted from message_analytics.py and report.py.
"""
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.engine.models import (
    Conversation, ConversationStats, HuddleEvent, MessageBookend, ThreadParticipation,
    UserDirectory,
)
from src.engine.mentions import extract_mentions

# ---------------------------------------------------------------------------
# Shared regex (lifted from message_analytics.py)
# ---------------------------------------------------------------------------
SYSTEM_SUBTYPES = {
    "huddle_thread", "channel_join", "channel_leave", "channel_topic",
    "channel_purpose", "channel_name", "bot_message", "bot_add",
    "bot_remove", "file_comment", "file_mention",
    "pinned_item", "unpinned_item", "group_join", "group_leave",
    "group_topic", "group_purpose", "group_name", "channel_archive",
    "channel_unarchive", "ekm_access_denied", "reminder_add",
    "sh_room_created", "tombstone",
}

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]*)?>")
_LINK_RE = re.compile(r"<https?://[^>]+>")
_EMOJI_RE = re.compile(r":[a-zA-Z0-9_+-]+:")
_EMOJI_EXTRACT_RE = re.compile(r":([a-zA-Z0-9_+-]+):")
_WORD_TOKEN_RE = re.compile(r"[a-zA-Z]{3,}")


def _clean_text(text: str) -> str:
    """Strip code blocks, inline code, mentions, links, emoji from text."""
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _MENTION_RE.sub("", text)
    text = _LINK_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    return text.strip()


def _strip_code_blocks(text: str) -> str:
    text = _CODE_BLOCK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    return text


def _filter_user_messages(messages: list[dict]) -> list[dict]:
    return [
        m for m in messages
        if m.get("subtype") not in SYSTEM_SUBTYPES
        and m.get("user") is not None
        and m.get("user") != "USLACKBOT"
    ]


def _ts_to_dt(ts: float, tz: ZoneInfo | None) -> datetime:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    if tz:
        dt = dt.astimezone(tz)
    else:
        dt = dt.astimezone()  # system local
    return dt


# ---------------------------------------------------------------------------
# Individual stat computations
# ---------------------------------------------------------------------------

def compute_volume(
    user_msgs: list[dict],
) -> tuple[dict[str, int], dict[str, int], dict[str, float]]:
    """Returns (message_count_by_user, word_count_by_user, avg_words_by_user)."""
    msg_count: Counter[str] = Counter()
    word_count: dict[str, int] = defaultdict(int)
    word_lists: dict[str, list[int]] = defaultdict(list)

    for m in user_msgs:
        uid = m["user"]
        msg_count[uid] += 1
        cleaned = _clean_text(m.get("text", ""))
        wc = len(cleaned.split()) if cleaned else 0
        word_count[uid] += wc
        word_lists[uid].append(wc)

    avg_words: dict[str, float] = {}
    for uid, words in word_lists.items():
        nonzero = [w for w in words if w > 0] or [0]
        avg_words[uid] = round(sum(nonzero) / len(nonzero), 1)

    return dict(msg_count), dict(word_count), avg_words


def compute_time_series(
    user_msgs: list[dict],
    tz: ZoneInfo | None,
) -> tuple[dict[date, int], dict[int, int], dict[int, int], dict[tuple[int, int], int]]:
    """Returns (messages_by_day, messages_by_dow, messages_by_hour, messages_by_dow_hour)."""
    by_day: Counter[date] = Counter()
    by_dow: Counter[int] = Counter()
    by_hour: Counter[int] = Counter()
    by_dow_hour: Counter[tuple[int, int]] = Counter()

    for m in user_msgs:
        ts = float(m["ts"])
        dt = _ts_to_dt(ts, tz)
        d = dt.date()
        by_day[d] += 1
        by_dow[dt.weekday()] += 1
        by_hour[dt.hour] += 1
        by_dow_hour[(dt.weekday(), dt.hour)] += 1

    return dict(by_day), dict(by_dow), dict(by_hour), dict(by_dow_hour)


def compute_thread_stats(
    user_msgs: list[dict],
    cached_threads: dict[str, dict],
) -> tuple[dict[str, int], list[ThreadParticipation]]:
    """Returns (threads_started_by_user, thread_participations)."""
    started: Counter[str] = Counter()
    for m in user_msgs:
        if m.get("reply_count", 0) > 0:
            started[m["user"]] += 1

    participations = []
    for root_ts, data in cached_threads.items():
        participants = data.get("participants", [])
        if participants:
            participations.append(ThreadParticipation(
                root_ts=float(root_ts),
                participants=frozenset(participants),
            ))

    return dict(started), participations


def compute_huddle_stats(
    huddles: list[HuddleEvent],
    me_id: str,
) -> tuple[int, int, dict[str, int]]:
    """Returns (huddle_count, huddle_seconds, huddle_partner_seconds)."""
    count = len(huddles)
    total_seconds = sum(h.duration_seconds for h in huddles)

    partner_seconds: Counter[str] = Counter()
    for h in huddles:
        if me_id in h.participants:
            for other in h.participants:
                if other != me_id:
                    partner_seconds[other] += h.duration_seconds

    return count, total_seconds, dict(partner_seconds)


def compute_word_frequencies(
    user_msgs: list[dict],
    n: int = 20,
) -> dict[str, Counter]:
    """Returns word_freq_by_user — Counter of top words per user."""
    freqs: dict[str, Counter] = defaultdict(Counter)
    for m in user_msgs:
        uid = m["user"]
        text = _strip_code_blocks(m.get("text", ""))
        text = _MENTION_RE.sub("", text)
        text = _LINK_RE.sub("", text)
        text = _EMOJI_RE.sub("", text)
        words = _WORD_TOKEN_RE.findall(text.lower())
        freqs[uid].update(words)
    return dict(freqs)


def compute_emoji_in_text(
    user_msgs: list[dict],
) -> dict[str, Counter]:
    """Returns emoji_in_text_by_user."""
    emojis: dict[str, Counter] = defaultdict(Counter)
    for m in user_msgs:
        uid = m["user"]
        text = _strip_code_blocks(m.get("text", ""))
        found = _EMOJI_EXTRACT_RE.findall(text)
        emojis[uid].update(found)
    return dict(emojis)


def compute_reactions(
    all_messages: list[dict],
) -> tuple[dict[str, Counter], dict[str, Counter]]:
    """Returns (reactions_given_by_user, reactions_received_by_user).

    given: user X reacted to someone's message → given[X][emoji] += 1
    received: someone reacted to user X's message → received[X][emoji] += 1
    """
    given: dict[str, Counter] = defaultdict(Counter)
    received: dict[str, Counter] = defaultdict(Counter)

    for m in all_messages:
        msg_author = m.get("user")
        for reaction in m.get("reactions", []):
            name = reaction.get("name", "")
            for uid in reaction.get("users", []):
                given[uid][name] += 1
                if msg_author:
                    received[msg_author][name] += 1

    return dict(given), dict(received)


def compute_links_files(
    user_msgs: list[dict],
) -> tuple[dict[str, int], dict[str, int]]:
    """Returns (links_by_user, files_by_user)."""
    links: Counter[str] = Counter()
    files: Counter[str] = Counter()
    for m in user_msgs:
        uid = m["user"]
        links[uid] += len(_LINK_RE.findall(m.get("text", "")))
        files[uid] += m.get("files_count", 0)
    return dict(links), dict(files)


def compute_mentions(
    all_messages: list[dict],
    user_directory: UserDirectory,
) -> dict[str, Counter]:
    """Returns mentions_made_by_user[sender_id][target_id] = count."""
    bot_lookup = {uid: u.is_bot for uid, u in user_directory.users.items()}
    mentions: dict[str, Counter] = defaultdict(Counter)

    for m in all_messages:
        sender = m.get("user")
        if not sender or sender not in bot_lookup or bot_lookup.get(sender, True):
            continue
        if m.get("subtype") in SYSTEM_SUBTYPES:
            continue
        text = m.get("text", "")
        extracted = extract_mentions(text, sender, bot_lookup)
        if extracted:
            mentions[sender].update(extracted)

    return dict(mentions)


def compute_bookends(
    conversation: Conversation,
    user_msgs: list[dict],
) -> tuple[MessageBookend | None, MessageBookend | None]:
    """Returns (first_message, last_message) within the filtered messages."""
    if not user_msgs:
        return None, None

    sorted_msgs = sorted(user_msgs, key=lambda m: float(m["ts"]))
    first = sorted_msgs[0]
    last = sorted_msgs[-1]

    def _bookend(m: dict) -> MessageBookend:
        return MessageBookend(
            ts=float(m["ts"]),
            user_id=m.get("user", ""),
            conversation_id=conversation.id,
            conversation_name=conversation.name,
            text_preview=(m.get("text") or "")[:80],
        )

    return _bookend(first), _bookend(last)


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def compute_conversation_stats(
    conversation: Conversation,
    me_id: str,
    window_start: datetime,
    window_end: datetime,
    user_directory: UserDirectory,
    tz: ZoneInfo | None = None,
    cached_threads: dict[str, dict] | None = None,
) -> ConversationStats:
    """
    Compute all per-conversation stats from a Conversation dataclass.

    This is the single entry point for the engine. All sub-computations
    are pure functions that return typed data.
    """
    if cached_threads is None:
        cached_threads = {}

    # Filter to window and user messages
    w_start = window_start.timestamp()
    w_end = window_end.timestamp()

    windowed = [
        m for m in conversation.messages
        if m.get("ts") and w_start <= float(m["ts"]) <= w_end
    ]
    user_msgs = _filter_user_messages(windowed)

    # Compute all stats
    msg_count, word_count, avg_words = compute_volume(user_msgs)
    by_day, by_dow, by_hour, by_dow_hour = compute_time_series(user_msgs, tz)
    threads_started, thread_participations = compute_thread_stats(user_msgs, cached_threads)
    huddle_count, huddle_seconds, huddle_partner = compute_huddle_stats(conversation.huddles, me_id)
    word_freq = compute_word_frequencies(user_msgs)
    emoji_text = compute_emoji_in_text(user_msgs)
    reactions_given, reactions_received = compute_reactions(windowed)
    links, files = compute_links_files(user_msgs)
    mentions = compute_mentions(windowed, user_directory)
    first_msg, last_msg = compute_bookends(conversation, user_msgs)

    return ConversationStats(
        conversation=conversation,
        me_id=me_id,
        window_start=window_start,
        window_end=window_end,
        message_count_by_user=msg_count,
        word_count_by_user=word_count,
        avg_words_by_user=avg_words,
        messages_by_day=by_day,
        messages_by_dow=by_dow,
        messages_by_hour=by_hour,
        messages_by_dow_hour=by_dow_hour,
        threads_started_by_user=threads_started,
        thread_participations=thread_participations,
        huddle_count=huddle_count,
        huddle_seconds=huddle_seconds,
        huddle_partner_seconds=huddle_partner,
        word_freq_by_user=word_freq,
        emoji_in_text_by_user=emoji_text,
        reactions_given_by_user=reactions_given,
        reactions_received_by_user=reactions_received,
        links_by_user=links,
        files_by_user=files,
        mentions_made_by_user=mentions,
        first_message=first_msg,
        last_message=last_msg,
    )
