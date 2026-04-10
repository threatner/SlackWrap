from src.engine.models import User, UserDirectory, Conversation, HuddleEvent, ThreadParticipation


class TestUser:
    def test_user_fields(self):
        u = User(id="U001", name="Alice", is_bot=False, is_deleted=False)
        assert u.id == "U001"
        assert u.name == "Alice"

    def test_user_is_frozen(self):
        u = User(id="U001", name="Alice", is_bot=False, is_deleted=False)
        try:
            u.name = "Bob"
            assert False, "should be frozen"
        except Exception:
            pass


class TestUserDirectory:
    def test_resolves_users_by_id(self):
        d = UserDirectory(
            users={
                "U001": User(id="U001", name="Alice", is_bot=False, is_deleted=False),
                "U002": User(id="U002", name="Bob", is_bot=True, is_deleted=False),
            },
            me_id="U_ME",
        )
        assert d.users["U001"].name == "Alice"
        assert d.users["U002"].is_bot is True
        assert d.me_id == "U_ME"


class TestConversation:
    def test_im_with_counterparty(self):
        c = Conversation(
            id="D001", kind="im", name="Alice", is_archived=False,
            member_ids=frozenset({"U_ME", "U001"}), counterparty_id="U001",
            messages=[{"user": "U001", "ts": "1.0", "text": "hi"}], huddles=[],
        )
        assert c.kind == "im"
        assert c.counterparty_id == "U001"

    def test_channel_no_counterparty(self):
        c = Conversation(
            id="C001", kind="public", name="engineering", is_archived=False,
            member_ids=frozenset({"U_ME", "U001", "U002"}), counterparty_id=None,
            messages=[], huddles=[],
        )
        assert c.counterparty_id is None


class TestHuddleEvent:
    def test_huddle_fields(self):
        h = HuddleEvent(
            started_ts=1700000000.0, duration_seconds=3600,
            participants=frozenset({"U_ME", "U001"}), started_by="U_ME",
        )
        assert h.duration_seconds == 3600
        assert "U_ME" in h.participants


class TestThreadParticipation:
    def test_thread_participation_fields(self):
        tp = ThreadParticipation(
            root_ts=1700000000.0,
            participants=frozenset({"U_ME", "U001", "U002"}),
        )
        assert len(tp.participants) == 3
