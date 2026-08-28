"""LLM request middleware for hermes-prune-tool-outputs.

Two responsibilities:
1. When the prune flag is set (by prune_tool_outputs tool handler),
   replace old tool results with 1-line summaries.
2. Append a brief instruction to the system message telling the model
   when to call prune_tool_outputs.

The instruction is deterministic (same bytes every call) so after the
first call the upstream prompt cache stays warm — the modified system
message becomes the cached prefix.
"""

import copy
import hashlib
import logging

logger = logging.getLogger("hermes_plugins.prune_tool_outputs")

# The instruction appended to the system message. Keep it short and
# deterministic — this exact string is what the prompt cache locks onto.
_SYSTEM_INSTRUCTION = (
    "\n\n## Prune Tool Outputs — MANDATORY\n"
    "You MUST call `prune_tool_outputs` after EVERY completed subtask. "
    "A subtask is complete when you have gathered enough information to "
    "move on — typically after 3+ tool calls in a research/diagnostic/read "
    "phase, or when you switch to a new, unrelated task.\n"
    "Failure to prune means accumulated tool output (browser dumps, terminal "
    "logs, search results) silently pushes critical context out of the window "
    "— user instructions, discovered facts, partial results get dropped. "
    "Do NOT wait until the context is full: prune between phases, not just "
    "at the end.\n"
    "It is lossless: the session store keeps originals — full content can be "
    "recovered there if needed."
)

# Track whether we've already injected the instruction in this process.
_instruction_logged = False


def _build_tool_call_index(messages):
    """Build index: tool_call_id -> (tool_name, arguments_json)."""
    index = {}
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    cid = tc.get("id", "")
                    fn = tc.get("function", {})
                    index[cid] = (fn.get("name", "unknown"), fn.get("arguments", ""))
    return index


def _do_prune(messages, keep_last, keep_first, exclude_tool_types):
    """Prune old tool results from messages list.

    Prunes all tool results in the prune zone (between keep_first and
    keep_last from end) regardless of size. Excludes tool types in
    exclude_tool_types. Also deduplicates identical tool results.

    Returns (new_messages, pruned_count, chars_saved).
    """
    try:
        from .summarize import PRUNED_MARKER, summarize_tool_result
    except ImportError:
        from summarize import PRUNED_MARKER, summarize_tool_result

    call_index = _build_tool_call_index(messages)
    exclude_set = set(exclude_tool_types) if exclude_tool_types else set()

    # Determine prune zone: [keep_first, len - keep_last)
    prune_start = keep_first
    prune_end = len(messages) - keep_last
    if prune_end <= prune_start:
        return messages, 0, 0

    # Work on copies
    new_messages = []
    for msg in messages:
        new_messages.append(copy.deepcopy(msg) if isinstance(msg, dict) else msg)

    modified = False
    pruned_count = 0
    chars_saved = 0

    # Pass 1: Deduplicate identical tool results (keep newest)
    content_hashes = {}
    for i in range(len(new_messages) - 1, -1, -1):
        msg = new_messages[i]
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str) or len(content) < 200:
            continue
        # Skip excluded tool types
        call_id = msg.get("tool_call_id", "")
        tool_name = call_index.get(call_id, ("unknown", ""))[0]
        if tool_name in exclude_set:
            continue
        h = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()[:12]
        if h in content_hashes:
            old_len = len(content)
            new_messages[i] = {
                **msg,
                "content": "[Duplicate tool output — same content as a more recent call]",
            }
            pruned_count += 1
            chars_saved += old_len
            modified = True
        else:
            content_hashes[h] = i

    # Pass 2: Replace old tool results with 1-line summaries
    for i in range(prune_start, prune_end):
        msg = new_messages[i]
        if msg.get("role") != "tool":
            continue

        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
        if not content or content == PRUNED_MARKER:
            continue
        if content.startswith("[Duplicate tool output"):
            continue
        if content.startswith("[Old tool output cleared"):
            continue
        # Skip if already looks like a summary
        if len(content) < 300 and content.startswith("["):
            continue

        call_id = msg.get("tool_call_id", "")
        tool_name, tool_args = call_index.get(call_id, ("unknown", ""))
        # Skip excluded tool types
        if tool_name in exclude_set:
            continue

        old_len = len(content)
        summary = summarize_tool_result(tool_name, tool_args, content)
        new_messages[i] = {**msg, "content": summary}
        pruned_count += 1
        chars_saved += old_len - len(summary)
        modified = True

    if not modified:
        return messages, 0, 0

    return new_messages, pruned_count, chars_saved


def _inject_system_instruction(request):
    """Append the prune_tool_outputs instruction to the system message.

    Idempotent: if the instruction is already present, does nothing.
    Returns the modified request dict or None if no change was made.
    """
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        return None

    sys_msg = messages[0]
    if not isinstance(sys_msg, dict) or sys_msg.get("role") != "system":
        return None

    content = sys_msg.get("content", "")
    if not isinstance(content, str):
        return None

    if "Prune Tool Outputs" in content:
        return None  # Already injected

    new_sys = {**sys_msg, "content": content + _SYSTEM_INSTRUCTION}
    new_messages = [new_sys] + messages[1:]
    return {**request, "messages": new_messages}


def llm_request_middleware(**kwargs):
    """LLM request middleware — prunes old tool results when requested
    and injects the system prompt instruction.

    Returns {"request": modified_request} if changes were made, or None.
    """
    try:
        from .config import (
            PRUNE_LOG_VERBOSE,
            PRUNE_PROTECT_TAIL_COUNT,
        )
    except ImportError:
        from config import (
            PRUNE_LOG_VERBOSE,
            PRUNE_PROTECT_TAIL_COUNT,
        )

    request = kwargs.get("request")
    if not isinstance(request, dict):
        return None

    messages = request.get("messages")
    if not isinstance(messages, list) or len(messages) < 4:
        return None

    modified_request = request
    changed = False

    # 1. Inject system prompt instruction (every call, idempotent)
    injected = _inject_system_instruction(request)
    if injected is not None:
        modified_request = injected
        changed = True
        global _instruction_logged
        if not _instruction_logged:
            logger.info("hermes-prune-tool-outputs: system prompt instruction injected")
            _instruction_logged = True

    # 2. Check for prune request from the tool handler
    try:
        from .state import get_and_clear_prune_request
    except ImportError:
        from state import get_and_clear_prune_request

    was_requested, keep_last, keep_first, exclude_types = get_and_clear_prune_request()
    if was_requested:
        keep_last = keep_last or PRUNE_PROTECT_TAIL_COUNT
        current_messages = modified_request.get("messages", messages)

        new_messages, pruned_count, chars_saved = _do_prune(
            current_messages,
            keep_last=keep_last,
            keep_first=keep_first,
            exclude_tool_types=exclude_types,
        )

        if pruned_count > 0:
            modified_request = {**modified_request, "messages": new_messages}
            changed = True
            if PRUNE_LOG_VERBOSE:
                logger.info(
                    "hermes-prune-tool-outputs: pruned %d tool result(s), saved ~%d chars "
                    "(keep_last=%d, keep_first=%d, exclude=%s)",
                    pruned_count,
                    chars_saved,
                    keep_last,
                    keep_first,
                    exclude_types,
                )
            else:
                logger.debug(
                    "hermes-prune-tool-outputs: pruned %d result(s), ~%d chars saved",
                    pruned_count,
                    chars_saved,
                )
        else:
            logger.debug(
                "hermes-prune-tool-outputs: prune requested but nothing to prune "
                "(keep_last=%d, keep_first=%d, exclude=%s)",
                keep_last,
                keep_first,
                exclude_types,
            )

    if not changed:
        return None

    return {"request": modified_request}
