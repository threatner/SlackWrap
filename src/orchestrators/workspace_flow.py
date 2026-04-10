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
import json
import os
import threading
import time

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text
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


def _build_live_table(
    phase: str,
    total: int,
    completed: int,
    failed: int,
    active_channels: dict[str, str],
    total_msgs: int,
    throttle_status: dict[str, str] | None = None,
) -> Table:
    """Build a rich Table that updates in-place — no scrolling."""
    table = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
    table.add_column(ratio=1)
    table.add_column(ratio=1, justify="right")

    table.add_row(
        Text("SlackWrap", style="bold cyan"),
        Text(phase, style="dim"),
    )
    table.add_row("", "")

    if total > 0:
        pct = int(completed / total * 100)
        bar_filled = pct // 2
        bar_empty = 50 - bar_filled
        bar = f"[cyan]{'█' * bar_filled}[/][dim]{'░' * bar_empty}[/] {pct}%"
        table.add_row(
            Text(f"  Conversations: {completed}/{total}  (failed: {failed})", style="white"),
            Text(f"Messages cached: {total_msgs:,}", style="green"),
        )
        table.add_row(f"  {bar}", "")
    else:
        table.add_row("  Discovering...", "")

    # Rate limit status
    if throttle_status:
        parts = []
        for tier, status in sorted(throttle_status.items()):
            if "waiting" in status or "⏳" in status:
                parts.append(f"[yellow]{tier}: {status}[/]")
            else:
                parts.append(f"[dim]{tier}: {status}[/]")
        if parts:
            table.add_row("", "")
            table.add_row(f"  Rate limits: {' │ '.join(parts)}", "")

    table.add_row("", "")
    if active_channels:
        for ch_name, status in list(active_channels.items())[:4]:
            table.add_row(
                Text(f"  ↳ {ch_name[:35]}", style="dim"),
                Text(status, style="dim cyan"),
            )
    return table


def run_workspace_fetch(
    client,
    cache: CacheManager,
    window_start_ts: str,
    window_end_ts: str,
    workers: int = 4,
    show_progress: bool = True,
) -> dict:
    """
    Top-level workspace fetch orchestrator with clean in-place progress UI.
    """
    from src.slack_client import _display as slack_display

    workers = _clamp_workers(workers)
    console = Console(stderr=True)

    # Mute the old per-message status display during workspace fetch
    if show_progress:
        slack_display.muted = True

    try:
        return _run_workspace_fetch_inner(
            client, cache, window_start_ts, window_end_ts, workers, show_progress, console,
        )
    finally:
        if show_progress:
            slack_display.muted = False


def _run_workspace_fetch_inner(
    client, cache, window_start_ts, window_end_ts, workers, show_progress, console,
) -> dict:
    # Phase A: discover
    directory, in_scope, out_of_scope = discover_workspace(client)
    persist_manifest(cache, me_id=directory.me_id, in_scope=in_scope, out_of_scope=out_of_scope)

    # Persist users list
    users_path = os.path.join(cache.cache_dir, "_users.json")
    with open(users_path, "w") as uf:
        json.dump(
            [{"id": u.id, "name": u.name, "is_bot": u.is_bot, "deleted": u.is_deleted,
              "profile": {"display_name": u.name}}
             for u in directory.users.values()],
            uf,
        )

    # Phase B + C: fetch + walk threads
    failures: list[dict] = []
    fetched_count = 0
    total_msgs_cached = 0
    failures_lock = threading.Lock()
    active_channels: dict[str, str] = {}
    active_lock = threading.Lock()

    def _process_one(entry: dict) -> tuple[bool, dict | None, int]:
        ch_name = entry["name"][:35]
        with active_lock:
            active_channels[ch_name] = "fetching..."
        try:
            msgs = fetch_conversation_messages(
                client, cache,
                channel_id=entry["id"],
                window_start_ts=window_start_ts,
                window_end_ts=window_end_ts,
            )
            msg_count = len(msgs)
            with active_lock:
                active_channels[ch_name] = f"{msg_count:,} msgs, walking threads..."
            walk_threads_for_conversation(
                client, cache,
                channel_id=entry["id"],
                me_id=directory.me_id,
            )
            return True, None, msg_count
        except Exception as e:
            return False, {"channel_id": entry["id"], "name": entry["name"], "error": str(e)}, 0
        finally:
            with active_lock:
                active_channels.pop(ch_name, None)

    if show_progress and in_scope:
        with Live(
            _build_live_table("Discovering...", 0, 0, 0, {}, 0),
            console=console,
            refresh_per_second=4,
        ) as live:
            live.update(_build_live_table(
                f"Fetching ({workers} workers)",
                len(in_scope), 0, 0, {}, 0, client.throttle_status,
            ))

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_process_one, entry): entry for entry in in_scope}
                for fut in concurrent.futures.as_completed(futures):
                    ok, failure, msg_count = fut.result()
                    if ok:
                        fetched_count += 1
                        total_msgs_cached += msg_count
                    else:
                        with failures_lock:
                            failures.append(failure)
                    with active_lock:
                        snapshot = dict(active_channels)
                    live.update(_build_live_table(
                        f"Fetching ({workers} workers)",
                        len(in_scope), fetched_count + len(failures), len(failures),
                        snapshot, total_msgs_cached, client.throttle_status,
                    ))

        # Final summary (printed once after live display ends)
        console.print()
        console.print(f"  [bold cyan]SlackWrap[/] fetch complete")
        console.print(f"  [green]{fetched_count}[/] conversations  |  [green]{total_msgs_cached:,}[/] messages  |  [red]{len(failures)}[/] failed")
        if failures:
            for f in failures:
                console.print(f"  [red]✗[/] {f['name']}: {f['error']}")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_one, entry): entry for entry in in_scope}
            for fut in concurrent.futures.as_completed(futures):
                ok, failure, msg_count = fut.result()
                if ok:
                    fetched_count += 1
                    total_msgs_cached += msg_count
                else:
                    with failures_lock:
                        failures.append(failure)

    return {
        "fetched_count": fetched_count,
        "failed_count": len(failures),
        "failures": failures,
        "in_scope": in_scope,
        "directory": directory,
    }


# ---------------------------------------------------------------------------
# Full workspace wrap: fetch → engine → aggregate → format
# ---------------------------------------------------------------------------

def run_workspace_wrap(client, cache: CacheManager, args) -> None:
    """
    End-to-end workspace wrap: fetch data, compute stats, aggregate, render.
    Prints console report and writes HTML file.
    """
    import sys
    from zoneinfo import ZoneInfo
    from src.engine.conversation_stats import compute_conversation_stats
    from src.engine.workspace_stats import aggregate_workspace_stats
    from src.reports.workspace_console import format_workspace_console
    from src.reports.workspace_html import render_workspace_html

    try:
        window_start_ts, window_end_ts = parse_window(
            year=args.year, from_str=args.from_date, to_str=args.to_date,
        )
    except ValueError as e:
        print(f"\n  Bad window: {e}")
        sys.exit(1)

    window_start = datetime.fromtimestamp(float(window_start_ts), tz=timezone.utc)
    window_end = datetime.fromtimestamp(float(window_end_ts), tz=timezone.utc)

    tz = None
    if args.timezone:
        try:
            tz = ZoneInfo(args.timezone)
        except Exception:
            print(f"  Warning: unknown timezone '{args.timezone}', using system local")

    # Phase 1: fetch (always runs — incremental, only pulls new messages)
    # The fetch itself is cheap when cache is warm (empty delta per channel).
    # Discovery (users.list + conversations.list) is the only real cost,
    # and that's 2-3 Tier 2 calls — acceptable for data freshness.
    result = run_workspace_fetch(
        client, cache,
        window_start_ts=window_start_ts, window_end_ts=window_end_ts,
        workers=args.workers, show_progress=True,
    )

    directory = result["directory"]
    in_scope = result["in_scope"]
    failures = result["failures"]

    # Phase 2: compute per-conversation stats
    console = Console(stderr=True)
    console.print("[dim]Computing stats...[/]")

    conversation_stats = []
    for entry in in_scope:
        cached = cache.load(entry["id"])
        if not cached:
            continue
        cached_threads = cached.get("threads", {})
        conv = load_conversation_from_cache(cache, entry, member_ids=frozenset())
        cs = compute_conversation_stats(
            conv, directory.me_id,
            window_start=window_start, window_end=window_end,
            user_directory=directory, tz=tz,
            cached_threads=cached_threads,
        )
        conversation_stats.append(cs)

    # Phase 4: aggregate
    failed_tuples = [(f["channel_id"], f["error"]) for f in failures]
    ws = aggregate_workspace_stats(
        conversation_stats, directory,
        failed_conversations=failed_tuples,
    )

    # Phase 5: render
    print(format_workspace_console(ws))

    html = render_workspace_html(ws)
    me_slug = ws.me.name.lower().replace(" ", "_")
    start_str = window_start.strftime("%Y-%m-%d")
    end_str = window_end.strftime("%Y-%m-%d")
    filename = f"slackwrap_{me_slug}_{start_str}_to_{end_str}.html"
    with open(filename, "w") as f:
        f.write(html)

    abs_path = os.path.abspath(filename)
    file_url = f"file://{abs_path}"
    print(f"\n  HTML report: {file_url}")
