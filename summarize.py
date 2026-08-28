# hermes-prune-tool-outputs: model-initiated tool output pruning for Hermes Agent.
# Copyright (C) 2026  Alik Aslanyan <inline0@pm.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Summarize tool results into informative 1-line descriptions.

Kept self-contained so the plugin survives core updates independently.

Summaries are intentionally compact: they never quote result content —
only a length note. Queries, paths, commands and other long arguments
are compacted (whitespace-collapsed + truncated) via _truncate().
"""

import json
import re

# Compactness knobs (chars) for embedded arguments/queries.
_TEXT_LIMIT = 50  # queries, paths, goals, questions, ids
_CMD_LIMIT = 80  # shell commands (a bit more room)
_CODE_PREVIEW_LIMIT = 60  # code previews
_GENERIC_ARG_LIMIT = 20  # generic fallback key=value pairs


def _truncate(text, limit: int) -> str:
    """Compact any value into a single-line string of at most `limit` chars.

    Collapses whitespace/newlines (long JSON or multi-line arguments become
    one line) and appends an ellipsis when truncated.
    """
    text = " ".join(str(text).split()) if text else ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _parse_args(tool_args: str | None) -> dict:
    """Parse the tool-call arguments JSON, tolerating malformed input."""
    try:
        args = json.loads(tool_args) if tool_args else {}
    except (json.JSONDecodeError, TypeError):
        return {}
    return args if isinstance(args, dict) else {}


def _len_note(content) -> str:
    """Compact length note for a tool result, e.g. '1,234 chars' / 'empty'."""
    n = len(content or "")
    return f"{n:,} chars" if n else "empty"


def summarize_tool_result(tool_name: str, tool_args: str, tool_content) -> str:
    """Create an informative 1-line summary of a tool call + result.

    Always reports the result LENGTH, never its content, e.g.:
        [terminal] `pytest -q` -> exit 0 (12,345 chars)
        [read_file] config.py from line 1 (12,345 chars)
        [web_search] 'context pruning' (5,555 chars)
    """
    args = _parse_args(tool_args)
    content = tool_content or ""
    note = _len_note(content)

    if tool_name == "terminal":
        cmd = _truncate(args.get("command", ""), _CMD_LIMIT)
        exit_match = re.search(r'"exit_code"\s*:\s*(-?\d+)', content)
        exit_code = exit_match.group(1) if exit_match else "?"
        return f"[terminal] `{cmd}` -> exit {exit_code} ({note})"

    if tool_name == "read_file":
        path = _truncate(args.get("path", "?"), _TEXT_LIMIT)
        offset = args.get("offset", 1)
        return f"[read_file] {path} from line {offset} ({note})"

    if tool_name == "write_file":
        path = _truncate(args.get("path", "?"), _TEXT_LIMIT)
        written = args.get("content", "")
        lines = written.count("\n") + 1 if written else "?"
        return f"[write_file] {path} ({lines} lines written)"

    if tool_name == "search_files":
        pattern = _truncate(args.get("pattern", "?"), _TEXT_LIMIT)
        path = _truncate(args.get("path", "."), _TEXT_LIMIT)
        target = args.get("target", "content")
        match = re.search(r'"total_count"\s*:\s*(\d+)', content)
        count = match.group(1) if match else "?"
        return f"[search_files] {target} '{pattern}' in {path} -> {count} matches"

    if tool_name == "patch":
        path = _truncate(args.get("path", "?"), _TEXT_LIMIT)
        mode = args.get("mode", "replace")
        return f"[patch] {mode} {path} ({note})"

    if tool_name.startswith("browser_"):
        url = _truncate(args.get("url", ""), _TEXT_LIMIT)
        ref = args.get("ref", "")
        detail = f" {url}" if url else (f" ref={ref}" if ref else "")
        return f"[{tool_name}]{detail} ({note})"

    if tool_name == "web_search":
        query = _truncate(args.get("query", "?"), _TEXT_LIMIT)
        return f"[web_search] '{query}' ({note})"

    if tool_name == "web_extract":
        urls = args.get("urls", [])
        if not isinstance(urls, list) or not urls:
            urls = ["?"]
        url_desc = _truncate(urls[0], _TEXT_LIMIT)
        if len(urls) > 1:
            url_desc += f" (+{len(urls) - 1} more)"
        return f"[web_extract] {url_desc} ({note})"

    if tool_name == "delegate_task":
        goal = _truncate(args.get("goal", ""), _TEXT_LIMIT)
        return f"[delegate_task] '{goal}' ({note})"

    if tool_name == "execute_code":
        code = _truncate(args.get("code", ""), _CODE_PREVIEW_LIMIT)
        return f"[execute_code] `{code}` ({note})"

    if tool_name in {"skill_view", "skills_list", "skill_manage"}:
        name = _truncate(args.get("name", "?"), _TEXT_LIMIT)
        return f"[{tool_name}] {name} ({note})"

    if tool_name == "vision_analyze":
        question = _truncate(args.get("question", ""), _TEXT_LIMIT)
        return f"[vision_analyze] '{question}' ({note})"

    if tool_name == "memory":
        action = args.get("action", "?")
        target = _truncate(args.get("target", "?"), _TEXT_LIMIT)
        return f"[memory] {action} on {target}"

    if tool_name == "todo":
        return "[todo] task list updated"

    if tool_name == "clarify":
        return "[clarify] asked the user a question"

    if tool_name == "text_to_speech":
        return f"[text_to_speech] audio ({note})"

    if tool_name == "cronjob":
        return f"[cronjob] {args.get('action', '?')}"

    if tool_name == "process":
        action = args.get("action", "?")
        sid = _truncate(args.get("session_id", "?"), _TEXT_LIMIT)
        return f"[process] {action} session={sid}"

    if tool_name == "session_search":
        query = _truncate(args.get("query", "?"), _TEXT_LIMIT)
        return f"[session_search] '{query}' ({note})"

    # Generic fallback: up to two non-empty arguments, truncated, + length note.
    parts = " ".join(
        f"{k}={_truncate(v, _GENERIC_ARG_LIMIT)}" for k, v in list(args.items())[:2] if v
    )
    detail = f" {parts}" if parts else ""
    return f"[{tool_name}]{detail} ({note})"


# Already-pruned marker — skip these on subsequent passes
PRUNED_MARKER = "[Old tool output cleared to save context space]"
