"""
Workspace aggregator — pure function that takes list[ConversationStats] +
UserDirectory → WorkspaceStats with all leaderboards, mentions, trends.

Per spec §7: all computation uses typed dataclasses, no I/O, no Slack calls.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from src.engine.models import (
    ConversationStats, UserDirectory, User,
    PersonInteraction, ChannelRanking, MentionCount, ChannelMentionCount,
    HeroStats, PeopleSection, ChannelsSection, HuddlesSection,
    MessagesSection, MentionsSection, TrendsSection, WorkspaceStats,
    StreakInfo, DayInfo, MonthInfo, MessageBookend,
)


# ---------------------------------------------------------------------------
# Internal accumulator
# ---------------------------------------------------------------------------

@dataclass
class _PersonAcc:
    dm_messages_exchanged: int = 0
    huddle_seconds: int = 0
    thread_coparticipations: int = 0
    last_seen_ts: float = 0.0


def _compute_interaction_score(acc: _PersonAcc) -> float:
    return (
        acc.dm_messages_exchanged
        + (acc.huddle_seconds / 60)
        + (acc.thread_coparticipations * 2)
    )


# ---------------------------------------------------------------------------
# People accumulation (spec §7.1)
# ---------------------------------------------------------------------------

def _accumulate_people(
    stats_list: list[ConversationStats],
    me_id: str,
) -> dict[str, _PersonAcc]:
    accumulators: dict[str, _PersonAcc] = defaultdict(_PersonAcc)

    for cs in stats_list:
        conv = cs.conversation

        if conv.kind == "im" and conv.counterparty_id:
            # 1:1 DM — all messages count
            cp = conv.counterparty_id
            total = sum(cs.message_count_by_user.values())
            accumulators[cp].dm_messages_exchanged += total
            # Huddles in 1:1 DM
            for h in conv.huddles:
                if me_id in h.participants:
                    for other in h.participants:
                        if other != me_id:
                            accumulators[other].huddle_seconds += h.duration_seconds
            # Last seen
            if cs.last_message:
                accumulators[cp].last_seen_ts = max(accumulators[cp].last_seen_ts, cs.last_message.ts)

        # Thread co-participation (all conversation types)
        for tp in cs.thread_participations:
            if me_id in tp.participants:
                for other in tp.participants:
                    if other != me_id:
                        accumulators[other].thread_coparticipations += 1
                        accumulators[other].last_seen_ts = max(accumulators[other].last_seen_ts, tp.root_ts)

    return dict(accumulators)


# ---------------------------------------------------------------------------
# Leaderboard builders
# ---------------------------------------------------------------------------

def _build_person_interaction(uid: str, acc: _PersonAcc, directory: UserDirectory) -> PersonInteraction | None:
    user = directory.users.get(uid)
    if not user or user.is_bot or uid == directory.me_id:
        return None
    return PersonInteraction(
        user=user,
        dm_messages_exchanged=acc.dm_messages_exchanged,
        huddle_seconds=acc.huddle_seconds,
        thread_coparticipations=acc.thread_coparticipations,
        interaction_score=_compute_interaction_score(acc),
        last_seen_ts=acc.last_seen_ts,
    )


def _build_people_section(
    accumulators: dict[str, _PersonAcc],
    directory: UserDirectory,
    window_end: datetime,
    prior_people_uids: set[str] | None = None,
) -> PeopleSection:
    all_interactions = []
    for uid, acc in accumulators.items():
        pi = _build_person_interaction(uid, acc, directory)
        if pi and pi.interaction_score > 0:
            all_interactions.append(pi)

    by_score = sorted(all_interactions, key=lambda p: (-p.interaction_score, p.user.name))
    by_dm = sorted([p for p in all_interactions if p.dm_messages_exchanged > 0],
                   key=lambda p: (-p.dm_messages_exchanged, p.user.name))
    by_huddle = sorted([p for p in all_interactions if p.huddle_seconds > 0],
                       key=lambda p: (-p.huddle_seconds, p.user.name))
    by_thread = sorted([p for p in all_interactions if p.thread_coparticipations > 0],
                       key=lambda p: (-p.thread_coparticipations, p.user.name))

    # Rediscovery: interaction_score > 0 but last_seen > 90 days ago
    cutoff_ts = (window_end - timedelta(days=90)).timestamp()
    rediscovery = sorted(
        [p for p in all_interactions if p.last_seen_ts < cutoff_ts],
        key=lambda p: (p.interaction_score, p.user.name),
    )

    # New / lost people (vs prior window)
    current_uids = {p.user.id for p in all_interactions}
    if prior_people_uids is not None:
        new_people = [directory.users[uid] for uid in current_uids - prior_people_uids if uid in directory.users]
        lost_people = [directory.users[uid] for uid in prior_people_uids - current_uids if uid in directory.users]
    else:
        new_people = []
        lost_people = []

    return PeopleSection(
        top_by_interaction=by_score[:10],
        top_by_dm_volume=by_dm[:10],
        top_by_huddle_time=by_huddle[:5],
        top_by_thread_coparticipation=by_thread[:5],
        rediscovery=rediscovery[:5],
        new_people=sorted(new_people, key=lambda u: u.name),
        lost_people=sorted(lost_people, key=lambda u: u.name),
    )


def _build_channels_section(
    stats_list: list[ConversationStats],
    me_id: str,
) -> ChannelsSection:
    rankings = []
    count_by_type: Counter[str] = Counter()

    for cs in stats_list:
        conv = cs.conversation
        count_by_type[conv.kind] += 1
        if conv.kind not in ("public", "private", "connect"):
            continue
        my = cs.message_count_by_user.get(me_id, 0)
        total = sum(cs.message_count_by_user.values())
        rankings.append(ChannelRanking(
            conversation_id=conv.id, name=conv.name, kind=conv.kind,
            my_message_count=my, total_message_count=total,
        ))

    by_mine = sorted(rankings, key=lambda r: (-r.my_message_count, r.name))
    by_total = sorted(rankings, key=lambda r: (-r.total_message_count, r.name))
    lurkers = sorted([r for r in rankings if r.my_message_count == 0], key=lambda r: r.name)

    return ChannelsSection(
        top_by_my_messages=by_mine[:10],
        top_by_total_volume=by_total[:10],
        lurker_channels=lurkers,
        count_by_type=dict(count_by_type),
    )


def _build_huddles_section(
    stats_list: list[ConversationStats],
    accumulators: dict[str, _PersonAcc],
    directory: UserDirectory,
) -> HuddlesSection:
    total_huddles = sum(cs.huddle_count for cs in stats_list)
    total_seconds = sum(cs.huddle_seconds for cs in stats_list)
    avg = total_seconds / total_huddles if total_huddles else 0.0

    # Partner leaderboard from accumulators (1:1 huddles)
    partners = []
    for uid, acc in accumulators.items():
        if acc.huddle_seconds > 0:
            pi = _build_person_interaction(uid, acc, directory)
            if pi:
                partners.append(pi)
    partners.sort(key=lambda p: (-p.huddle_seconds, p.user.name))

    # Longest single huddle
    longest_secs = 0
    longest_partner = None
    for cs in stats_list:
        for h in cs.conversation.huddles:
            if h.duration_seconds > longest_secs:
                longest_secs = h.duration_seconds
                others = [uid for uid in h.participants if uid != directory.me_id]
                longest_partner = directory.users.get(others[0]) if others else None

    return HuddlesSection(
        total_huddles=total_huddles,
        total_seconds=total_seconds,
        avg_seconds=avg,
        partner_leaderboard=partners[:10],
        longest_huddle_seconds=longest_secs,
        longest_huddle_partner=longest_partner,
    )


def _build_messages_section(
    stats_list: list[ConversationStats],
    me_id: str,
) -> MessagesSection:
    # Merge daily timelines
    merged_daily: Counter[date] = Counter()
    merged_dow_hour: Counter[tuple[int, int]] = Counter()
    merged_emoji: Counter[str] = Counter()
    merged_reactions_given: Counter[str] = Counter()
    merged_reactions_received: Counter[str] = Counter()
    merged_words: Counter[str] = Counter()
    total_word_count = 0
    total_msg_count = 0
    threads_started = 0
    threads_replied_in = 0
    links = 0
    files = 0
    first_msg: MessageBookend | None = None
    last_msg: MessageBookend | None = None

    for cs in stats_list:
        for d, cnt in cs.messages_by_day.items():
            merged_daily[d] += cnt
        for key, cnt in cs.messages_by_dow_hour.items():
            merged_dow_hour[key] += cnt

        if me_id in cs.emoji_in_text_by_user:
            merged_emoji.update(cs.emoji_in_text_by_user[me_id])
        if me_id in cs.reactions_given_by_user:
            merged_reactions_given.update(cs.reactions_given_by_user[me_id])
        if me_id in cs.reactions_received_by_user:
            merged_reactions_received.update(cs.reactions_received_by_user[me_id])
        if me_id in cs.word_freq_by_user:
            merged_words.update(cs.word_freq_by_user[me_id])

        total_word_count += cs.word_count_by_user.get(me_id, 0)
        total_msg_count += cs.message_count_by_user.get(me_id, 0)
        threads_started += cs.threads_started_by_user.get(me_id, 0)
        # Threads replied in: messages where thread_ts != ts and user == me
        for tp in cs.thread_participations:
            if me_id in tp.participants:
                threads_replied_in += 1
        links += cs.links_by_user.get(me_id, 0)
        files += cs.files_by_user.get(me_id, 0)

        # Bookends (workspace-wide first/last)
        if cs.first_message:
            if first_msg is None or cs.first_message.ts < first_msg.ts:
                first_msg = cs.first_message
        if cs.last_message:
            if last_msg is None or cs.last_message.ts > last_msg.ts:
                last_msg = cs.last_message

    avg_words = round(total_word_count / total_msg_count, 1) if total_msg_count else 0.0
    timeline = sorted(merged_daily.items())

    return MessagesSection(
        daily_volume_timeline=timeline,
        dow_hour_heatmap=dict(merged_dow_hour),
        top_emojis_in_text=merged_emoji.most_common(10),
        top_reactions_given=merged_reactions_given.most_common(10),
        top_reactions_received=merged_reactions_received.most_common(10),
        top_words=merged_words.most_common(20),
        avg_words_per_message=avg_words,
        threads_started=threads_started,
        threads_replied_in=threads_replied_in,
        links_shared=links,
        files_shared=files,
        first_message=first_msg,
        last_message=last_msg,
    )


def _build_mentions_section(
    stats_list: list[ConversationStats],
    me_id: str,
    directory: UserDirectory,
) -> MentionsSection:
    mentioners_of_me: Counter[str] = Counter()
    mentioned_by_me: Counter[str] = Counter()
    channel_mentions: Counter[str] = Counter()  # conv_id -> count

    for cs in stats_list:
        for sender, targets in cs.mentions_made_by_user.items():
            for target, count in targets.items():
                if target == me_id:
                    mentioners_of_me[sender] += count
                    if cs.conversation.kind in ("public", "private", "connect"):
                        channel_mentions[cs.conversation.id] += count
                if sender == me_id:
                    mentioned_by_me[target] += count

    total_received = sum(mentioners_of_me.values())
    total_made = sum(mentioned_by_me.values())

    top_mentioners = []
    for uid, count in mentioners_of_me.most_common(10):
        user = directory.users.get(uid)
        if user and not user.is_bot:
            top_mentioners.append(MentionCount(user=user, count=count))

    top_mentioned = []
    for uid, count in mentioned_by_me.most_common(10):
        user = directory.users.get(uid)
        if user and not user.is_bot:
            top_mentioned.append(MentionCount(user=user, count=count))

    # Channel mention hotspots
    top_channels = []
    for conv_id, count in channel_mentions.most_common(5):
        # Find the conversation name
        for cs in stats_list:
            if cs.conversation.id == conv_id:
                top_channels.append(ChannelMentionCount(
                    conversation_id=conv_id, name=cs.conversation.name, count=count,
                ))
                break

    return MentionsSection(
        total_mentions_received=total_received,
        top_mentioners_of_me=top_mentioners,
        total_mentions_made=total_made,
        top_people_i_mentioned=top_mentioned,
        top_channels_where_mentioned=top_channels,
    )


def _compute_streak(daily_counts: dict[date, int]) -> StreakInfo | None:
    """Find the longest consecutive-day streak with at least 1 message."""
    if not daily_counts:
        return None
    sorted_days = sorted(d for d, c in daily_counts.items() if c > 0)
    if not sorted_days:
        return None

    best_len = 1
    best_start = sorted_days[0]
    cur_len = 1
    cur_start = sorted_days[0]

    for i in range(1, len(sorted_days)):
        if sorted_days[i] == sorted_days[i - 1] + timedelta(days=1):
            cur_len += 1
        else:
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
            cur_len = 1
            cur_start = sorted_days[i]
    if cur_len > best_len:
        best_len = cur_len
        best_start = cur_start

    return StreakInfo(
        length_days=best_len,
        start_date=best_start,
        end_date=best_start + timedelta(days=best_len - 1),
    )


def _build_hero(
    stats_list: list[ConversationStats],
    accumulators: dict[str, _PersonAcc],
    me_id: str,
    directory: UserDirectory,
) -> HeroStats:
    total_msgs = sum(cs.message_count_by_user.get(me_id, 0) for cs in stats_list)
    total_huddle_secs = sum(cs.huddle_seconds for cs in stats_list)
    unique = sum(
        1 for uid, acc in accumulators.items()
        if _compute_interaction_score(acc) > 0
        and uid != me_id
        and uid in directory.users
        and not directory.users[uid].is_bot
    )
    active_convos = sum(1 for cs in stats_list if sum(cs.message_count_by_user.values()) > 0)

    # Merge daily for streak + busiest day
    merged_daily: Counter[date] = Counter()
    for cs in stats_list:
        for d, cnt in cs.messages_by_day.items():
            merged_daily[d] += cnt

    streak = _compute_streak(merged_daily)
    busiest = None
    if merged_daily:
        top_day, top_count = merged_daily.most_common(1)[0]
        busiest = DayInfo(date=top_day, message_count=top_count)

    return HeroStats(
        total_messages_sent=total_msgs,
        total_huddle_seconds=total_huddle_secs,
        unique_humans=unique,
        active_conversations=active_convos,
        longest_streak=streak,
        busiest_day=busiest,
    )


def _build_trends(
    current_hero: HeroStats,
    current_people_uids: set[str],
    current_mentions_received: int,
    prior_hero: HeroStats | None,
    prior_people_uids: set[str] | None,
    stats_list: list[ConversationStats],
    me_id: str,
) -> TrendsSection:
    # % changes vs prior
    msg_change = None
    huddle_change = None
    people_change = 0

    if prior_hero:
        if prior_hero.total_messages_sent > 0:
            msg_change = round(
                (current_hero.total_messages_sent - prior_hero.total_messages_sent)
                / prior_hero.total_messages_sent * 100, 1
            )
        if prior_hero.total_huddle_seconds > 0:
            huddle_change = round(
                (current_hero.total_huddle_seconds - prior_hero.total_huddle_seconds)
                / prior_hero.total_huddle_seconds * 100, 1
            )
        if prior_people_uids is not None:
            people_change = len(current_people_uids) - len(prior_people_uids)

    # Monthly activity
    monthly: Counter[tuple[int, int]] = Counter()
    for cs in stats_list:
        for d, cnt in cs.messages_by_day.items():
            monthly[(d.year, d.month)] += cnt

    most_active = None
    quietest = None
    if monthly:
        top = max(monthly.items(), key=lambda x: x[1])
        most_active = MonthInfo(year=top[0][0], month=top[0][1], message_count=top[1])
        bot = min(monthly.items(), key=lambda x: x[1])
        quietest = MonthInfo(year=bot[0][0], month=bot[0][1], message_count=bot[1])

    return TrendsSection(
        message_volume_change_pct=msg_change,
        huddle_time_change_pct=huddle_change,
        unique_people_change=people_change,
        most_active_month=most_active,
        quietest_month=quietest,
    )


# ---------------------------------------------------------------------------
# Top-level aggregator
# ---------------------------------------------------------------------------

def aggregate_workspace_stats(
    stats_list: list[ConversationStats],
    directory: UserDirectory,
    prior_stats: "WorkspaceStats | None" = None,
    failed_conversations: list[tuple[str, str]] | None = None,
) -> WorkspaceStats:
    """
    Aggregate per-conversation stats into workspace-wide stats.

    Pure function: no I/O, no Slack calls. Everything comes from
    the typed inputs.
    """
    me_id = directory.me_id
    me = directory.users.get(me_id, User(id=me_id, name="You", is_bot=False, is_deleted=False))

    # Get window from first stats entry
    if stats_list:
        window_start = stats_list[0].window_start
        window_end = stats_list[0].window_end
    else:
        window_start = datetime.now(timezone.utc)
        window_end = datetime.now(timezone.utc)

    # Accumulate people
    accumulators = _accumulate_people(stats_list, me_id)

    # Prior window data for trends + new/lost people
    prior_hero = prior_stats.hero if prior_stats else None
    prior_people_uids = None
    if prior_stats:
        prior_people_uids = {p.user.id for p in prior_stats.people.top_by_interaction}

    # Build all sections
    hero = _build_hero(stats_list, accumulators, me_id, directory)
    people = _build_people_section(accumulators, directory, window_end, prior_people_uids)
    channels = _build_channels_section(stats_list, me_id)
    huddles = _build_huddles_section(stats_list, accumulators, directory)
    messages = _build_messages_section(stats_list, me_id)
    mentions = _build_mentions_section(stats_list, me_id, directory)

    current_people_uids = {p.user.id for p in people.top_by_interaction}
    trends = _build_trends(
        hero, current_people_uids, mentions.total_mentions_received,
        prior_hero, prior_people_uids, stats_list, me_id,
    )

    return WorkspaceStats(
        me=me,
        window_start=window_start,
        window_end=window_end,
        hero=hero,
        people=people,
        channels=channels,
        huddles=huddles,
        messages=messages,
        mentions=mentions,
        trends=trends,
        failed_conversations=failed_conversations or [],
    )
