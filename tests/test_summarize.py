"""Unit tests for summarize.py."""

import json

import pytest

from summarize import (
    PRUNED_MARKER,
    _len_note,
    _parse_args,
    _truncate,
    summarize_tool_result,
)


class TestTruncate:
    def test_short_string_passthrough(self):
        assert _truncate("pytest", 50) == "pytest"

    def test_long_string_truncated_with_ellipsis(self):
        out = _truncate("x" * 200, 50)
        assert len(out) == 50
        assert out.endswith("…")

    def test_exactly_at_limit_not_truncated(self):
        assert _truncate("x" * 50, 50) == "x" * 50

    def test_whitespace_collapsed(self):
        assert _truncate("a\n\nb\t\tc   d", 50) == "a b c d"

    def test_multiline_json_becomes_single_line(self):
        out = _truncate('{"a": 1,\n "b": 2}', 50)
        assert "\n" not in out

    def test_none_and_empty(self):
        assert _truncate(None, 50) == ""
        assert _truncate("", 50) == ""

    def test_non_string_values_coerced(self):
        assert _truncate(12345, 50) == "12345"


class TestParseArgs:
    def test_valid_json(self):
        assert _parse_args('{"command": "ls"}') == {"command": "ls"}

    def test_empty(self):
        assert _parse_args("") == {}
        assert _parse_args(None) == {}

    def test_malformed_json(self):
        assert _parse_args("{not json") == {}

    def test_non_dict_json(self):
        assert _parse_args("[1, 2]") == {}


class TestLenNote:
    def test_empty(self):
        assert _len_note("") == "empty"
        assert _len_note(None) == "empty"

    def test_formatted(self):
        assert _len_note("x" * 1234) == "1,234 chars"


class TestSummaries:
    def test_terminal_exit_code_and_truncated_command(self):
        long_cmd = "pytest " + "-v " * 40
        out = summarize_tool_result("terminal", json.dumps({"command": long_cmd}), "out")
        assert out.startswith("[terminal] `pytest -v")
        assert len(out) < 140
        assert "-> exit ?" in out

    def test_terminal_exit_code_extracted(self):
        out = summarize_tool_result(
            "terminal", '{"command": "ls"}', '{"output": "...", "exit_code": 2}'
        )
        assert "-> exit 2" in out

    def test_read_file(self):
        out = summarize_tool_result("read_file", '{"path": "config.py", "offset": 10}', "x" * 500)
        assert out == "[read_file] config.py from line 10 (500 chars)"

    def test_write_file(self):
        out = summarize_tool_result(
            "write_file", '{"path": "a.py", "content": "l1\\nl2\\nl3"}', "ok"
        )
        assert out == "[write_file] a.py (3 lines written)"

    def test_search_files_count_extracted(self):
        out = summarize_tool_result(
            "search_files",
            '{"pattern": "foo", "path": "."}',
            '{"total_count": 12, "matches": []}',
        )
        assert "-> 12 matches" in out

    def test_patch(self):
        out = summarize_tool_result("patch", '{"path": "a.py"}', "x" * 100)
        assert out == "[patch] replace a.py (100 chars)"

    def test_browser_prefix_matching(self):
        out = summarize_tool_result("browser_navigate", '{"url": "https://example.com"}', "x" * 300)
        assert out == "[browser_navigate] https://example.com (300 chars)"

    def test_web_search_query_compacted(self):
        out = summarize_tool_result("web_search", json.dumps({"query": "very " * 30}), "x" * 900)
        assert out.startswith("[web_search] 'very very")
        assert out.endswith("(900 chars)")
        # Query portion is compacted to <= 50 chars (+ quotes/ellipsis).
        assert len(out) < 100

    def test_web_extract_multiple_urls(self):
        out = summarize_tool_result(
            "web_extract",
            '{"urls": ["https://a.com", "https://b.com", "https://c.com"]}',
            "x",
        )
        assert "https://a.com (+2 more)" in out

    def test_execute_code_multiline_collapsed(self):
        code = "def f():\n" * 20
        out = summarize_tool_result("execute_code", json.dumps({"code": code}), "out")
        assert "\n" not in out

    def test_generic_fallback_unknown_tool(self):
        out = summarize_tool_result("weird_tool", '{"alpha": "one", "beta": "two"}', "z" * 7)
        assert out == "[weird_tool] alpha=one beta=two (7 chars)"

    def test_generic_fallback_long_value_truncated(self):
        out = summarize_tool_result("weird_tool", json.dumps({"k": "v" * 100}), "")
        assert "k=vvv" in out
        assert "…" in out
        assert out.endswith("(empty)")


class TestCompactness:
    """Summaries must never leak result content and must stay short."""

    @pytest.mark.parametrize(
        "tool_name,args",
        [
            ("terminal", '{"command": "cat big.log"}'),
            ("read_file", '{"path": "big.log"}'),
            ("web_search", '{"query": "secrets"}'),
            ("web_extract", '{"urls": ["https://big.log"]}'),
            ("mystery_tool", '{"x": 1}'),
        ],
    )
    def test_never_contains_result_content(self, tool_name, args):
        big_output = "SECRET-PAYLOAD " * 500
        summary = summarize_tool_result(tool_name, args, big_output)
        assert "SECRET-PAYLOAD" not in summary
        assert "7,500 chars" in summary or "7,500" in summary

    def test_search_files_never_contains_result_content(self):
        # search_files reports the match count (if parseable), not a length note
        big_output = "SECRET-PAYLOAD " * 500
        summary = summarize_tool_result("search_files", '{"pattern": "secrets"}', big_output)
        assert "SECRET-PAYLOAD" not in summary
        assert len(summary) < 120

    def test_all_summaries_single_line(self):
        big = "line\n" * 100
        for name in ("terminal", "read_file", "web_search", "unknown_tool"):
            summary = summarize_tool_result(name, "{}", big)
            assert "\n" not in summary

    def test_pruned_marker_unchanged(self):
        assert PRUNED_MARKER == "[Old tool output cleared to save context space]"
