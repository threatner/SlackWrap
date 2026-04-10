"""
Workspace flow orchestrator.

Phase 1 implements the complete data acquisition pipeline:
  1. discover_workspace — enumerate users + conversations, filter, return scoping data
  2. persist_manifest — write discovery results preserving per-channel cache state
  3. fetch_conversation_messages — per-conversation window-bounded incremental fetch
  4. walk_threads_for_conversation — selective thread walking for co-participation
  5. run_workspace_fetch — top-level orchestrator (sequential or concurrent)
  6. parse_window — CLI argument parsing for time windows
  7. load_conversation_from_cache — cache -> Conversation dataclass
"""
import concurrent.futures
import threading
import time

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from datetime import datetime, timedelta, timezone

from src.cache import CacheManager
from src.engine.models import User, UserDirectory, Conversation, HuddleEvent


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _build_user_directory(users: list[dict], me_id: str) -> UserDirectory:
    user_records = {}
    for u in users:
        profile = u.get("profile", {})
        name = (
            profile.get("display_name")
            or u.get("real_name")
            or u.get("name")
            or u.get("id", "Unknown")
        )
        user_records[u["id"]] = User(
            id=u["id"],
            name=name,
            is_bot=bool(u.get("is_bot", False)) or u.get("id") == "USLACKBOT",
            is_deleted=bool(u.get("deleted", False)),
        )
    return UserDirectory(users=user_records, me_id=me_id)


def _classify_conversation(conv: dict, directory: UserDirectory) -> tuple[str, str | None]:
    """Classify a raw Slack conversation. Returns (kind, filter_reason). None = in scope."""
    if conv.get("is_im"):
        other = conv.get("user")
        if not other:
            return ("im", "missing_counterparty")
        other_user = directory.users.get(other)
        if other_user is None:
            return ("im", "unknown_user")
        if other_user.is_bot:
            return ("im", "bot_user")
        return ("im", None)

    if conv.get("is_mpim"):
        return ("mpim", None)

    if conv.get("is_member") is not True:
        kind = "private" if (conv.get("is_private") or conv.get("is_group")) else "public"
        return (kind, "not_a_member")

    if conv.get("is_ext_shared") or conv.get("is_org_shared"):
        return ("connect", None)
    if conv.get("is_private") or conv.get("is_group"):
        return ("private", None)
    if conv.get("is_channel"):
        return ("public", None)

    return ("public", "unknown_type")


def discover_workspace(client) -> tuple[UserDirectory, list[dict], list[dict]]:
    """
    Phase A: discover all users and conversations, classify and filter.

    Returns:
      - directory: UserDirectory
      - in_scope: list of dicts with id, kind, name, is_archived, counterparty_id, raw
      - out_of_scope: list of dicts with id, kind, name, filter_reason, raw
    """
    users = client.list_users()
    me_id = client.user_id
    directory = _build_user_directory(users, me_id)

    try:
        conversations = client.list_conversations(
            types="public_channel,private_channel,mpim,im",
            exclude_archived=False,
        )
    except RuntimeError as e:
        if "missing_scope" in str(e):
            raise RuntimeError(
                "Slack token is missing required scopes. Please add these User Token Scopes "
                "to your Slack app and reinstall:\n"
                "  - channels:read (list public channels)\n"
                "  - groups:read (list private channels)\n"
                "  - im:read (list DMs)\n"
                "  - mpim:read (list group DMs)\n"
                "  - mpim:history (read group DM messages)\n\n"
                "Go to https://api.slack.com/apps → your app → OAuth & Permissions"
            ) from e
        raise

    in_scope: list[dict] = []
    out_of_scope: list[dict] = []
    for conv in conversations:
        kind, reason = _classify_conversation(conv, directory)
        if reason is None:
            counterparty_id = conv.get("user") if kind == "im" else None
            name = conv.get("name") or (
                directory.users[counterparty_id].name
                if counterparty_id and counterparty_id in directory.users
                else conv.get("id", "")
            )
            in_scope.append({
                "id": conv["id"],
                "kind": kind,
                "name": name,
                "is_archived": bool(conv.get("is_archived", False)),
                "counterparty_id": counterparty_id,
                "raw": conv,
            })
        else:
            out_of_scope.append({
                "id": conv["id"],
                "kind": kind,
                "name": conv.get("name", conv.get("id", "")),
                "filter_reason": reason,
                "raw": conv,
            })

    return directory, in_scope, out_of_scope


# ---------------------------------------------------------------------------
# Manifest persistence
# ---------------------------------------------------------------------------

def persist_manifest(
    cache: CacheManager,
    me_id: str,
    in_scope: list[dict],
    out_of_scope: list[dict],
) -> None:
    """Write workspace manifest, preserving per-channel cache state from prior runs."""
    prior = cache.load_manifest() or {}
    prior_state = {c["id"]: c for c in prior.get("conversations", [])}

    conversations = []
    for entry in in_scope:
        prev = prior_state.get(entry["id"], {})
        conversations.append({
            "id": entry["id"],
            "kind": entry["kind"],
            "name": entry["name"],
            "is_archived": entry.get("is_archived", False),
            "counterparty_id": entry.get("counterparty_id"),
            "in_scope": True,
            "filter_reason": None,
            "oldest_cached_ts": prev.get("oldest_cached_ts", "0"),
            "newest_cached_ts": prev.get("newest_cached_ts", "0"),
            "last_fetched_ts": prev.get("last_fetched_ts", 0),
        })
    for entry in out_of_scope:
        conversations.append({
            "id": entry["id"],
            "kind": entry["kind"],
            "name": entry["name"],
            "in_scope": False,
            "filter_reason": entry["filter_reason"],
        })

    manifest = {
        "version": 1,
        "discovered_at": int(time.time()),
        "me_id": me_id,
        "conversations": conversations,
    }
    cache.save_manifest(manifest)


# ---------------------------------------------------------------------------
# Per-conversation message fetch (bidirectional window)
# ---------------------------------------------------------------------------

def _ts_float(ts: str | None) -> float:
    """Safely convert a Slack timestamp string to float for comparison."""
    try:
        return float(ts) if ts else 0.0
    except (ValueError, TypeError):
        return 0.0


def fetch_conversation_messages(
    client,
    cache: CacheManager,
    channel_id: str,
    window_start_ts: str,
    window_end_ts: str,
) -> list[dict]:
    """
    Window-bounded incremental fetch with bidirectional backfill.

    Two passes:
      1. Backfill: if window_start < oldest_cached_ts, fetch [window_start, oldest_cached_ts)
      2. Forward: fetch [max(newest_cached_ts, window_start), ∞) for new messages

    All timestamp comparisons use float to avoid lexicographic string bugs.
    """
    w_start = _ts_float(window_start_ts)
    w_end = _ts_float(window_end_ts)
    cached = cache.load(channel_id)

    # Pass 1: backfill if needed
    if cached is not None and w_start < _ts_float(cached.get("oldest_cached_ts", "0")):
        backfill_latest = cached["oldest_cached_ts"]
        raw = client.fetch_messages(
            channel_id,
            oldest=window_start_ts,
            latest=backfill_latest,
            include_threads=False,
        )
        backfilled = [CacheManager.trim_message(m) for m in raw]
        backfilled = [m for m in backfilled if m.get("ts") and _ts_float(m["ts"]) < _ts_float(backfill_latest)]
        if backfilled:
            existing_ts = {m["ts"] for m in cached["messages"]}
            truly_new = [m for m in backfilled if m["ts"] not in existing_ts]
            if truly_new:
                cache.append(channel_id, truly_new, last_ts=cached.get("last_ts", "0"))
                cached = cache.load(channel_id)

    # Pass 2: forward fetch
    if cached is None:
        forward_oldest = window_start_ts
    else:
        newest = _ts_float(cached.get("newest_cached_ts", "0"))
        forward_oldest = cached.get("newest_cached_ts", "0") if newest >= w_start else window_start_ts

    raw = client.fetch_messages(
        channel_id,
        oldest=forward_oldest,
        include_threads=False,
    )
    new_msgs = [CacheManager.trim_message(m) for m in raw]
    new_msgs = [m for m in new_msgs if m.get("ts") and w_start <= _ts_float(m["ts"]) <= w_end]

    if cached is None:
        if new_msgs:
            latest_ts = max(new_msgs, key=lambda m: _ts_float(m["ts"]))["ts"]
            cache.save(channel_id, new_msgs, last_ts=latest_ts)
        else:
            cache.save(channel_id, [], last_ts=window_end_ts)
    else:
        existing_ts = {m["ts"] for m in cached["messages"]}
        truly_new = [m for m in new_msgs if m["ts"] not in existing_ts]
        if truly_new:
            latest_new_ts = max(
                max(_ts_float(m["ts"]) for m in truly_new),
                _ts_float(cached.get("last_ts", "0")),
            )
            cache.append(channel_id, truly_new, last_ts=f"{latest_new_ts:.1f}")

    refreshed = cache.load(channel_id) or {"messages": []}
    return [m for m in refreshed["messages"] if w_start <= _ts_float(m.get("ts", "0")) <= w_end]


# ---------------------------------------------------------------------------
# Selective thread walker
# ---------------------------------------------------------------------------

def walk_threads_for_conversation(
    client,
    cache: CacheManager,
    channel_id: str,
    me_id: str,
) -> None:
    """
    Walk thread replies only for threads the user participated in.
    Builds the "threads to walk" set from cached messages, calls
    conversations.replies only for those, persists participant set +
    latest_reply to the per-channel cache.
    """
    cached = cache.load(channel_id)
    if cached is None:
        return

    threads_to_walk: dict[str, str] = {}  # root_ts -> Slack-reported latest_reply

    for msg in cached["messages"]:
        if msg.get("user") != me_id:
            continue
        ts = msg.get("ts")
        if not ts:
            continue
        if msg.get("reply_count", 0) > 0:
            threads_to_walk.setdefault(ts, msg.get("latest_reply", ""))
        thread_ts = msg.get("thread_ts")
        if thread_ts and thread_ts != ts:
            threads_to_walk.setdefault(thread_ts, "")

    cached_threads = cached.get("threads", {})

    for root_ts, slack_latest_reply in threads_to_walk.items():
        prior = cached_threads.get(root_ts)
        if prior is not None:
            if slack_latest_reply and slack_latest_reply <= prior.get("latest_reply", ""):
                continue
            if not slack_latest_reply:
                continue

        replies = client.fetch_thread_replies(channel_id, root_ts)
        participants = sorted({r["user"] for r in replies if r.get("user")})
        latest_reply = max((r["ts"] for r in replies if r.get("ts")), default=root_ts)
        cache.save_thread_participants(
            channel_id,
            thread_ts=root_ts,
            participants=participants,
            latest_reply=latest_reply,
        )


# ---------------------------------------------------------------------------
# Conversation loader (cache -> Conversation dataclass)
# ---------------------------------------------------------------------------

def _extract_huddles(messages: list[dict]) -> list[HuddleEvent]:
    huddles = []
    for m in messages:
        if m.get("subtype") != "huddle_thread":
            continue
        room = m.get("room") or {}
        if not room.get("has_ended"):
            continue
        date_start = room.get("date_start")
        date_end = room.get("date_end")
        if not date_start or not date_end:
            continue
        duration = int(date_end) - int(date_start)
        if duration <= 0:
            continue
        huddles.append(HuddleEvent(
            started_ts=float(date_start),
            duration_seconds=duration,
            participants=frozenset(room.get("participant_history") or []),
            started_by=room.get("created_by", ""),
        ))
    return huddles


def load_conversation_from_cache(
    cache: CacheManager,
    manifest_entry: dict,
    member_ids: frozenset[str],
) -> Conversation:
    cached = cache.load(manifest_entry["id"])
    messages = cached["messages"] if cached else []
    huddles = _extract_huddles(messages)
    return Conversation(
        id=manifest_entry["id"],
        kind=manifest_entry["kind"],
        name=manifest_entry["name"],
        is_archived=manifest_entry.get("is_archived", False),
        member_ids=member_ids,
        counterparty_id=manifest_entry.get("counterparty_id"),
        messages=messages,
        huddles=huddles,
    )


# ---------------------------------------------------------------------------
# Window parsing
# ---------------------------------------------------------------------------

def parse_window(
    year: int | None,
    from_str: str | None,
    to_str: str | None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Parse CLI window arguments into (window_start_ts, window_end_ts) strings."""
    if now is None:
        now = datetime.now(timezone.utc)

    if year is not None:
        start_dt = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime(year, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
    elif from_str or to_str:
        if from_str:
            start_dt = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start_dt = now - timedelta(days=365)
        if to_str:
            end_dt = datetime.strptime(to_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
            )
        else:
            end_dt = now
        if start_dt > end_dt:
            raise ValueError(f"--from ({from_str}) is after --to ({to_str})")
    else:
        start_dt = now - timedelta(days=365)
        end_dt = now

    return f"{start_dt.timestamp():.6f}", f"{end_dt.timestamp():.6f}"


# ---------------------------------------------------------------------------
# Top-level fetch orchestrator
# ---------------------------------------------------------------------------

def _clamp_workers(n: int) -> int:
    return max(1, min(n, 8))


def run_workspace_fetch(
    client,
    cache: CacheManager,
    window_start_ts: str,
    window_end_ts: str,
    workers: int = 4,
    show_progress: bool = True,
) -> dict:
    """
    Top-level workspace fetch orchestrator.

    Pipeline:
      1. Discover users + conversations + filter
      2. Persist manifest
      3. For each in-scope conversation: fetch messages + walk threads
      4. Per-conversation error isolation

    Returns dict with fetched_count, failed_count, failures, in_scope, directory.
    """
    workers = _clamp_workers(workers)
    console = Console(stderr=True)

    if show_progress:
        console.print(f"[bold cyan]SlackWrap[/] — workspace fetch (workers={workers})")

    # Phase A: discover
    if show_progress:
        console.print("[dim]Discovering users and conversations...[/]")
    directory, in_scope, out_of_scope = discover_workspace(client)
    persist_manifest(cache, me_id=directory.me_id, in_scope=in_scope, out_of_scope=out_of_scope)
    if show_progress:
        console.print(
            f"[green]Discovered[/] {len(in_scope)} in-scope "
            f"({len(out_of_scope)} filtered out)"
        )

    # Phase B + C: fetch + walk threads (concurrent)
    failures: list[dict] = []
    fetched_count = 0
    failures_lock = threading.Lock()

    def _process_one(entry: dict, progress: Progress | None, task_id) -> tuple[bool, dict | None]:
        try:
            fetch_conversation_messages(
                client, cache,
                channel_id=entry["id"],
                window_start_ts=window_start_ts,
                window_end_ts=window_end_ts,
            )
            walk_threads_for_conversation(
                client, cache,
                channel_id=entry["id"],
                me_id=directory.me_id,
            )
            return True, None
        except Exception as e:
            return False, {"channel_id": entry["id"], "name": entry["name"], "error": str(e)}
        finally:
            if progress is not None and task_id is not None:
                progress.update(task_id, advance=1)

    if show_progress and in_scope:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Fetching conversations", total=len(in_scope))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_process_one, entry, progress, task_id): entry for entry in in_scope}
                for fut in concurrent.futures.as_completed(futures):
                    ok, failure = fut.result()
                    if ok:
                        fetched_count += 1
                    else:
                        with failures_lock:
                            failures.append(failure)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_one, entry, None, None): entry for entry in in_scope}
            for fut in concurrent.futures.as_completed(futures):
                ok, failure = fut.result()
                if ok:
                    fetched_count += 1
                else:
                    with failures_lock:
                        failures.append(failure)

    if show_progress:
        console.print(f"[green]Fetch complete:[/] {fetched_count} succeeded, {len(failures)} failed")
        if failures:
            console.print("[red]Failed channels:[/]")
            for f in failures:
                console.print(f"  - {f['name']} ({f['channel_id']}): {f['error']}")

    return {
        "fetched_count": fetched_count,
        "failed_count": len(failures),
        "failures": failures,
        "in_scope": in_scope,
        "directory": directory,
    }
