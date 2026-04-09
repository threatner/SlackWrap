from __future__ import annotations


def test_clean_text_strips_code_blocks():
    from slackwrap.analytics.text_processing import clean_text_for_words
    text = "hello ```def foo(): pass``` world"
    result = clean_text_for_words(text)
    assert "def" not in result
    assert "hello" in result
    assert "world" in result


def test_clean_text_strips_mentions():
    from slackwrap.analytics.text_processing import clean_text_for_words
    text = "hey <@U12345> check this"
    result = clean_text_for_words(text)
    assert "U12345" not in result
    assert "hey" in result


def test_clean_text_strips_links():
    from slackwrap.analytics.text_processing import clean_text_for_words
    text = "see <https://example.com|this link> here"
    result = clean_text_for_words(text)
    assert "https" not in result
    assert "see" in result


def test_clean_text_strips_emoji():
    from slackwrap.analytics.text_processing import clean_text_for_words
    text = "great job :thumbsup: :rocket:"
    result = clean_text_for_words(text)
    assert "thumbsup" not in result
    assert "great" in result


def test_count_words():
    from slackwrap.analytics.text_processing import count_words
    assert count_words("The quick brown fox jumps") == 5


def test_count_words_strips_markup():
    from slackwrap.analytics.text_processing import count_words
    text = "hello ```code block``` world <@U123>"
    assert count_words(text) == 2


def test_extract_emojis():
    from slackwrap.analytics.text_processing import extract_emojis
    text = "hey :rocket: nice :thumbsup: stuff"
    assert extract_emojis(text) == ["rocket", "thumbsup"]


def test_extract_emojis_ignores_code_blocks():
    from slackwrap.analytics.text_processing import extract_emojis
    text = "```code :not_emoji:``` real :rocket:"
    assert extract_emojis(text) == ["rocket"]


def test_count_links():
    from slackwrap.analytics.text_processing import count_links
    text = "see <https://example.com> and <https://other.com|link>"
    assert count_links(text) == 2


def test_top_words():
    from slackwrap.analytics.text_processing import top_words
    texts = ["the quick brown fox", "the lazy brown dog", "the quick red fox"]
    result = top_words(texts, n=3)
    words = [w for w, _ in result]
    assert "quick" in words
    assert "brown" in words
    assert "fox" in words


def test_classify_message_length():
    from slackwrap.analytics.text_processing import classify_message_length
    assert classify_message_length(2) == "short"
    assert classify_message_length(15) == "medium"
    assert classify_message_length(50) == "long"
