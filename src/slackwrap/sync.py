from __future__ import annotations

import json
import time

from slackwrap.db import Database
from slackwrap.slack_client import SlackClient


class SyncEngine:
    def __init__(self, db: Database, client: SlackClient):
        self.db = db
        self.client = client

    def sync_user(self, slack_id: str) -> int:
        info = self.client.fetch_user_info(slack_id)
        profile = self.client.fetch_user_profile(slack_id)
        user_id = self.db.upsert_user(
            slack_id=info.get("id", slack_id),
            name=info.get("name"),
            display_name=info.get("profile", {}).get("display_name"),
            real_name=info.get("real_name"),
            is_bot=info.get("is_bot", False),
            timezone=info.get("tz"),
            tz_offset=info.get("tz_offset"),
            title=profile.get("title"),
            start_date=self._extract_start_date(profile),
            status_text=profile.get("status_text"),
            status_emoji=profile.get("status_emoji"),
            locale=info.get("locale"),
            avatar_url=info.get("profile", {}).get("image_72"),
        )
        self.db.commit()
        return user_id

    def _extract_start_date(self, profile: dict) -> str | None:
        fields = profile.get("fields") or {}
        for field_data in fields.values():
            label = (field_data.get("label") or "").lower()
            if "start" in label and "date" in label:
                return field_data.get("value")
        return None

    def sync_channel(self, slack_id: str) -> int:
        info = self.client.fetch_conversation_info(slack_id)
        ch_id = self.db.upsert_channel(
            slack_id=info.get("id", slack_id),
            name=info.get("name"),
            type=self._channel_type(info),
            created_at=info.get("created"),
            topic=info.get("topic", {}).get("value") if isinstance(info.get("topic"), dict) else info.get("topic"),
            purpose=info.get("purpose", {}).get("value") if isinstance(info.get("purpose"), dict) else info.get("purpose"),
            num_members=info.get("num_members"),
            is_archived=info.get("is_archived", False),
        )
        self.db.commit()
        return ch_id

    def _channel_type(self, info: dict) -> str:
        if info.get("is_im"):
            return "dm"
        if info.get("is_mpim"):
            return "mpim"
        if info.get("is_group") or info.get("is_private"):
            return "group"
        return "channel"

    def sync_channel_messages(self, channel_slack_id: str) -> int:
        ch_id = self.db.get_channel_id(channel_slack_id)
        if ch_id is None:
            ch_id = self.db.upsert_channel(slack_id=channel_slack_id)
            self.db.commit()

        # Check sync state for delta sync
        state = self.db.execute(
            "SELECT * FROM sync_state WHERE channel_id = ?", (ch_id,)
        ).fetchone()
        oldest = None
        if state and state["last_synced_ts"]:
            oldest = state["last_synced_ts"]

        # Mark as syncing
        self.db.execute(
            """INSERT INTO sync_state (channel_id, status) VALUES (?, 'syncing')
               ON CONFLICT(channel_id) DO UPDATE SET status='syncing'""",
            (ch_id,),
        )
        self.db.commit()

        # Fetch messages
        if oldest:
            raw_messages = self.client.fetch_messages_with_threads(
                channel_slack_id, oldest=oldest
            )
        else:
            raw_messages = self.client.fetch_messages_with_threads(channel_slack_id)

        count = 0
        latest_ts = oldest or ""

        for msg in raw_messages:
            ts = msg.get("ts", "")
            user_slack_id = msg.get("user")

            # Ensure user exists in DB
            user_id = None
            if user_slack_id:
                user_id = self.db.get_user_id(user_slack_id)
                if user_id is None:
                    user_id = self.db.upsert_user(
                        slack_id=user_slack_id, name=user_slack_id
                    )

            # Upsert message
            msg_id = self.db.upsert_message(
                channel_id=ch_id,
                user_id=user_id,
                slack_ts=ts,
                text=msg.get("text", ""),
                created_at=float(ts.split(".")[0]) if ts else 0.0,
                subtype=msg.get("subtype"),
                thread_ts=msg.get("thread_ts"),
                reply_count=msg.get("reply_count", 0),
                files_count=len(msg.get("files", [])),
            )

            # Extract reactions
            for reaction in msg.get("reactions", []):
                emoji_name = reaction.get("name", "")
                for uid in reaction.get("users", []):
                    r_user_id = self.db.get_user_id(uid)
                    if r_user_id is None:
                        r_user_id = self.db.upsert_user(slack_id=uid, name=uid)
                    self.db.execute(
                        "INSERT OR IGNORE INTO reactions (message_id, user_id, emoji_name) VALUES (?, ?, ?)",
                        (msg_id, r_user_id, emoji_name),
                    )

            # Extract huddles
            if msg.get("subtype") == "huddle_thread":
                room = msg.get("room", {})
                if room.get("has_ended"):
                    created_by = room.get("created_by")
                    created_by_id = None
                    if created_by:
                        created_by_id = self.db.get_user_id(created_by)
                        if created_by_id is None:
                            created_by_id = self.db.upsert_user(
                                slack_id=created_by, name=created_by
                            )
                    participants = room.get("participant_history", [])
                    started = room.get("date_start", 0)
                    ended = room.get("date_end", 0)
                    duration = int(ended - started)
                    self.db.execute(
                        """INSERT OR IGNORE INTO huddles
                           (channel_id, created_by_user_id, started_at, ended_at,
                            duration_seconds, participant_ids)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            ch_id,
                            created_by_id,
                            started,
                            ended,
                            duration,
                            json.dumps(participants),
                        ),
                    )

            if ts > latest_ts:
                latest_ts = ts
            count += 1

        # Update sync state
        self.db.execute(
            """INSERT INTO sync_state (channel_id, last_synced_ts, last_synced_at, status)
               VALUES (?, ?, ?, 'complete')
               ON CONFLICT(channel_id) DO UPDATE SET
                   last_synced_ts=excluded.last_synced_ts,
                   last_synced_at=excluded.last_synced_at,
                   status='complete'""",
            (ch_id, latest_ts, time.time()),
        )
        self.db.commit()
        return count

    def sync_channel_pins(self, channel_slack_id: str) -> int:
        ch_id = self.db.get_channel_id(channel_slack_id)
        if ch_id is None:
            ch_id = self.db.upsert_channel(slack_id=channel_slack_id)
            self.db.commit()

        pins = self.client.fetch_pins(channel_slack_id)
        count = 0
        for pin in pins:
            if pin.get("type") != "message":
                continue
            user_slack_id = pin.get("created_by")
            user_id = None
            if user_slack_id:
                user_id = self.db.get_user_id(user_slack_id)
                if user_id is None:
                    user_id = self.db.upsert_user(
                        slack_id=user_slack_id, name=user_slack_id
                    )
            msg_ts = pin.get("message", {}).get("ts")
            self.db.execute(
                "INSERT OR IGNORE INTO pins (channel_id, user_id, message_ts, pinned_at) VALUES (?, ?, ?, ?)",
                (ch_id, user_id, msg_ts, pin.get("created")),
            )
            count += 1
        self.db.commit()
        return count

    def sync_channel_files(self, channel_slack_id: str) -> int:
        ch_id = self.db.get_channel_id(channel_slack_id)
        if ch_id is None:
            ch_id = self.db.upsert_channel(slack_id=channel_slack_id)
            self.db.commit()

        files = self.client.fetch_files(channel=channel_slack_id)
        count = 0
        for f in files:
            user_slack_id = f.get("user")
            user_id = None
            if user_slack_id:
                user_id = self.db.get_user_id(user_slack_id)
                if user_id is None:
                    user_id = self.db.upsert_user(
                        slack_id=user_slack_id, name=user_slack_id
                    )
            self.db.execute(
                """INSERT OR IGNORE INTO files
                   (channel_id, user_id, slack_file_id, name, filetype,
                    size_bytes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ch_id,
                    user_id,
                    f.get("id", ""),
                    f.get("name"),
                    f.get("filetype"),
                    f.get("size"),
                    f.get("created"),
                ),
            )
            count += 1
        self.db.commit()
        return count

    def sync_relationship(
        self, target_user_slack_id: str, include_shared_channels: bool = True
    ) -> dict:
        results = {
            "users": 0,
            "channels": 0,
            "messages": 0,
            "pins": 0,
            "files": 0,
        }

        self.sync_user(self.client.user_id)
        self.sync_user(target_user_slack_id)
        results["users"] = 2

        dm_channels = self.client.fetch_dm_channels()
        dm_channel = None
        for ch in dm_channels:
            if ch.get("user") == target_user_slack_id:
                dm_channel = ch
                break

        channels_to_sync = []
        if dm_channel:
            self.sync_channel(dm_channel["id"])
            channels_to_sync.append(dm_channel["id"])

        if include_shared_channels:
            shared = self.client.find_shared_channels(target_user_slack_id)
            for ch in shared:
                self.sync_channel(ch["id"])
                channels_to_sync.append(ch["id"])

        results["channels"] = len(channels_to_sync)

        for ch_id in channels_to_sync:
            results["messages"] += self.sync_channel_messages(ch_id)
            results["pins"] += self.sync_channel_pins(ch_id)
            results["files"] += self.sync_channel_files(ch_id)

        return results
