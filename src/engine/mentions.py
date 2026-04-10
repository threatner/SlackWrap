"""
Mention extraction utility.

Per spec §7.1.1:
- Skip self-mentions
- Skip mentions of bot users
- Skip mentions of unknown users
- @channel/@here/@everyone (<!channel>/<!here>/<!everyone>) don't match MENTION_RE
- Usergroup tokens (<!subteam^...>) don't match MENTION_RE
"""
import re
from collections import Counter

MENTION_RE = re.compile(r"<@([A-Z0-9_]+)(?:\|[^>]*)?>")


def extract_mentions(
    text: str,
    sender_id: str,
    bot_lookup: dict[str, bool],
) -> dict[str, int]:
    """
    Extract user mentions from text.

    bot_lookup: maps user_id -> is_bot. Unknown targets are skipped.
    Returns dict[target_user_id, count]. Empty if no valid mentions.
    """
    if not text:
        return {}
    counter: Counter = Counter()
    for target_id in MENTION_RE.findall(text):
        if target_id == sender_id:
            continue
        if target_id not in bot_lookup:
            continue
        if bot_lookup[target_id]:
            continue
        counter[target_id] += 1
    return dict(counter)
