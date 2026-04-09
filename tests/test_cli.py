# tests/test_cli.py
from __future__ import annotations


def test_cli_has_no_cache_flag():
    from slackwrap.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--no-cache"])
    assert args.no_cache is True


def test_cli_has_clear_cache_flag():
    from slackwrap.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--clear-cache"])
    assert args.clear_cache is True


def test_cli_has_web_only_flag():
    from slackwrap.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--web"])
    assert args.web is True


def test_cli_default_flags():
    from slackwrap.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([])
    assert args.no_cache is False
    assert args.clear_cache is False
    assert args.web is False
