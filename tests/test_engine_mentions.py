from src.engine.mentions import extract_mentions, MENTION_RE


class TestMentionRegex:
    def test_simple_mention(self):
        assert MENTION_RE.findall("hello <@U123>") == ["U123"]

    def test_mention_with_label(self):
        assert MENTION_RE.findall("hi <@U123|alice>") == ["U123"]

    def test_no_broadcast(self):
        assert MENTION_RE.findall("<!channel>") == []
        assert MENTION_RE.findall("<!here>") == []
        assert MENTION_RE.findall("<!everyone>") == []

    def test_no_subteam(self):
        assert MENTION_RE.findall("<!subteam^S123|@team>") == []

    def test_multiple(self):
        assert MENTION_RE.findall("<@U1> and <@U2>") == ["U1", "U2"]


class TestExtractMentions:
    def test_skips_self(self):
        result = extract_mentions("hey <@U_ME>", "U_ME", {"U_ME": False})
        assert result == {}

    def test_skips_bot_target(self):
        result = extract_mentions("<@BOT>", "U_ME", {"U_ME": False, "BOT": True})
        assert result == {}

    def test_skips_unknown(self):
        result = extract_mentions("<@UNKNOWN>", "U_ME", {"U_ME": False})
        assert result == {}

    def test_counts_multiple_same_user(self):
        result = extract_mentions("<@U001> reminder <@U001>", "U_ME", {"U_ME": False, "U001": False})
        assert result == {"U001": 2}

    def test_multiple_targets(self):
        result = extract_mentions("<@U001> and <@U002>", "U_ME", {"U_ME": False, "U001": False, "U002": False})
        assert result == {"U001": 1, "U002": 1}

    def test_empty_text(self):
        assert extract_mentions("", "U_ME", {"U_ME": False}) == {}
