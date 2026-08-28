"""Tool schema and handler for prune_tool_outputs.

The model calls this tool when it decides that previous tool results
are no longer needed and can be replaced with compact summaries to
save context space. The actual pruning happens on the next API call
via the llm_request middleware.
"""

import json
import logging
from typing import Any

logger = logging.getLogger("hermes_plugins.prune_tool_outputs")

TOOL_SCHEMA = {
    "name": "prune_tool_outputs",
    "description": (
        "MANDATORY: Call after every completed subtask to replace old tool results "
        "with compact 1-line summaries, preventing context overflow. "
        "A subtask is done when you've finished gathering info (3+ tool calls) "
        "and are switching topics or about to deliver results. "
        "All old tool results in the prune zone are replaced regardless of size. "
        "Lossless: originals are kept in the session store. "
        "Do NOT wait until context is full — prune proactively between phases."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keep_last_n_messages": {
                "type": "integer",
                "description": (
                    "Number of recent messages to protect from pruning (default: 12). "
                    "Everything before this tail is eligible for pruning. "
                    "Set lower to prune more aggressively, higher to keep more context. "
                    "Minimum: 2 (must always keep at least the last 2 messages). "
                    "Maximum: 500 (no point keeping more)."
                ),
            },
            "keep_first_n_messages": {
                "type": "integer",
                "description": (
                    "Number of messages from the start of the conversation to protect from "
                    "pruning (default: 0). Useful to preserve the initial user request and "
                    "early context that sets the task framing. "
                    "Minimum: 0. Maximum: 100. "
                    "Must be less than keep_last_n_messages — if the two zones overlap or "
                    "touch, nothing gets pruned and the call is a no-op."
                ),
            },
            "exclude_tool_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Tool names whose results should NOT be pruned. "
                    'Example: ["memory", "session_search"]. '
                    "Matching is exact (case-sensitive) against the tool function name "
                    "as it appears in tool_calls. Default: none excluded. "
                    "Each entry must be a non-empty string. Duplicates are ignored."
                ),
            },
        },
        "required": [],
    },
}

# ─── Validation constants ───────────────────────────────────────────────
_KEEP_LAST_MIN = 2
_KEEP_LAST_MAX = 500
_KEEP_FIRST_MIN = 0
_KEEP_FIRST_MAX = 100
_EXCLUDE_MAX_ENTRIES = 50


def _error(message: str, **extra) -> str:
    """Return a structured error response for the model."""
    payload = {"pruned": False, "error": True, "message": message}
    payload.update(extra)
    logger.warning("prune_tool_outputs validation error: %s", message)
    return json.dumps(payload)


def _validate_keep_last(
    raw: Any, fallback: int, field_name: str, deprecated_field: str = None
) -> tuple[int | None, str | None]:
    """Validate keep_last_n_messages / keep_recent.

    Returns (value, error_message). If value is None, no value was provided
    and the caller should use the fallback.
    """
    if raw is None and deprecated_field is not None:
        raw = deprecated_field

    if raw is None:
        return None, None

    if isinstance(raw, bool):
        return None, (
            f"Invalid '{field_name}': received boolean {raw}. "
            f"Expected an integer between {_KEEP_LAST_MIN} and {_KEEP_LAST_MAX}. "
            "This field controls how many recent messages to protect from pruning."
        )

    if isinstance(raw, str):
        try:
            raw = int(raw)
        except ValueError:
            return None, (
                f"Invalid '{field_name}': received string \"{raw}\". "
                f"Pass an integer between {_KEEP_LAST_MIN} and {_KEEP_LAST_MAX}. "
                "Example: keep_last_n_messages=12 (protects last 12 messages)."
            )

    if not isinstance(raw, (int, float)):
        return None, (
            f"Invalid '{field_name}': received {type(raw).__name__}. "
            f"Expected an integer between {_KEEP_LAST_MIN} and {_KEEP_LAST_MAX}."
        )

    raw = int(raw)

    if raw < _KEEP_LAST_MIN:
        return None, (
            f"Invalid '{field_name}': value {raw} is below minimum {_KEEP_LAST_MIN}. "
            "At least 2 recent messages must always be protected. "
            f"Use {_KEEP_LAST_MIN} or higher. Clamped to {_KEEP_LAST_MIN}."
        )

    if raw > _KEEP_LAST_MAX:
        return None, (
            f"Invalid '{field_name}': value {raw} exceeds maximum {_KEEP_LAST_MAX}. "
            "Keeping more than 500 recent messages defeats the purpose of pruning. "
            f"Use {_KEEP_LAST_MAX} or lower. Clamped to {_KEEP_LAST_MAX}."
        )

    return raw, None


def _validate_keep_first(raw: Any) -> tuple[int | None, str | None]:
    """Validate keep_first_n_messages.

    Returns (value, error_message). None value = not provided.
    """
    if raw is None:
        return None, None

    if isinstance(raw, bool):
        return None, (
            f"Invalid 'keep_first_n_messages': received boolean {raw}. "
            f"Expected an integer between {_KEEP_FIRST_MIN} and {_KEEP_FIRST_MAX}. "
            "This field protects the first N messages from pruning "
            "(e.g. to preserve the original user request)."
        )

    if isinstance(raw, str):
        try:
            raw = int(raw)
        except ValueError:
            return None, (
                f"Invalid 'keep_first_n_messages': received string \"{raw}\". "
                f"Pass an integer between {_KEEP_FIRST_MIN} and {_KEEP_FIRST_MAX}. "
                "Example: keep_first_n_messages=2 (protects first 2 messages)."
            )

    if not isinstance(raw, (int, float)):
        return None, (
            f"Invalid 'keep_first_n_messages': received {type(raw).__name__}. "
            f"Expected an integer between {_KEEP_FIRST_MIN} and {_KEEP_FIRST_MAX}."
        )

    raw = int(raw)

    if raw < _KEEP_FIRST_MIN:
        return None, (
            f"Invalid 'keep_first_n_messages': value {raw} is below minimum {_KEEP_FIRST_MIN}. "
            "Negative values are not allowed. Use 0 (default, protects nothing) or higher."
        )

    if raw > _KEEP_FIRST_MAX:
        return None, (
            f"Invalid 'keep_first_n_messages': value {raw} exceeds maximum {_KEEP_FIRST_MAX}. "
            "Protecting more than 100 initial messages leaves almost no prune zone. "
            f"Use {_KEEP_FIRST_MAX} or lower."
        )

    return raw, None


def _validate_exclude_tool_types(raw: Any) -> tuple[list[str], str | None]:
    """Validate exclude_tool_types.

    Returns (clean_list, error_message). On error, clean_list is empty
    but the error guides the model — the call proceeds with no exclusions
    so the model can retry with correct syntax.
    """
    if raw is None:
        return [], None

    if not isinstance(raw, list):
        return [], (
            f"Invalid 'exclude_tool_types': received {type(raw).__name__}, "
            "expected a list of strings. "
            'Example: exclude_tool_types=["memory", "session_search"]. '
            "Each entry must be a tool name (exact, case-sensitive match)."
        )

    if len(raw) == 0:
        return [], None

    if len(raw) > _EXCLUDE_MAX_ENTRIES:
        return [], (
            f"Invalid 'exclude_tool_types': list has {len(raw)} entries, "
            f"maximum is {_EXCLUDE_MAX_ENTRIES}. "
            "You probably don't need to exclude this many tools."
        )

    cleaned = []
    errors = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, (str, int)):
            errors.append(f"entry [{i}] is {type(entry).__name__}, expected string")
            continue
        s = str(entry).strip()
        if not s:
            errors.append(f"entry [{i}] is empty string")
            continue
        if s not in cleaned:
            cleaned.append(s)

    if errors:
        hint = (
            "Tool names are case-sensitive and match the function name in tool_calls. "
            'Common tool names to exclude: "memory", "session_search".'
        )
        return cleaned, (
            f"Invalid 'exclude_tool_types': {'; '.join(errors)}. {hint} "
            f"Valid entries were kept: {cleaned}."
        )

    return cleaned, None


def _validate_zone_overlap(
    keep_last: int, keep_first: int, total_messages_hint: int = None
) -> str | None:
    """Check if keep_first and keep_last zones overlap, leaving no prune zone."""
    if total_messages_hint is not None:
        prune_zone_size = total_messages_hint - keep_last - keep_first
        if prune_zone_size <= 0:
            return (
                f"No prune zone available: keep_first_n_messages={keep_first} + "
                f"keep_last_n_messages={keep_last} = {keep_first + keep_last} protected, "
                f"but conversation only has {total_messages_hint} messages. "
                "Nothing to prune. Either reduce keep_last_n_messages, "
                "reduce keep_first_n_messages, or wait until the conversation grows longer."
            )
    return None


def handle_prune_tool_outputs(args: dict, **kwargs) -> str:
    """Tool handler — validates all parameters, then sets the prune-requested flag.

    The actual pruning is performed by the llm_request middleware on the
    next API call. This handler validates inputs, records the request,
    and returns a status message so the model knows the prune will happen.

    All validation errors return a JSON response with:
      - pruned: false
      - error: true
      - message: human-readable explanation + guidance on correct usage
    """
    try:
        from .config import PRUNE_PROTECT_TAIL_COUNT
    except ImportError:
        from config import PRUNE_PROTECT_TAIL_COUNT

    # ─── Collect all validation errors ───────────────────────────────
    errors = []
    warnings = []

    # 1. keep_last_n_messages (backward compat: also check keep_recent)
    keep_last_raw = args.get("keep_last_n_messages")
    keep_recent_raw = args.get("keep_recent")
    keep_last, err = _validate_keep_last(
        keep_last_raw,
        PRUNE_PROTECT_TAIL_COUNT,
        field_name="keep_last_n_messages",
        deprecated_field=keep_recent_raw,
    )
    if err:
        errors.append(err)
        # Use fallback but proceed — model gets the error to correct next time
        keep_last = PRUNE_PROTECT_TAIL_COUNT
    elif keep_last is None:
        keep_last = PRUNE_PROTECT_TAIL_COUNT

    # Warn if using deprecated field name
    if keep_last_raw is None and keep_recent_raw is not None:
        warnings.append(
            "'keep_recent' is deprecated — use 'keep_last_n_messages' instead. "
            "The value was accepted this time but may not be supported in future versions."
        )

    # 2. keep_first_n_messages
    keep_first_raw = args.get("keep_first_n_messages")
    keep_first, err = _validate_keep_first(keep_first_raw)
    if err:
        errors.append(err)
        keep_first = 0
    elif keep_first is None:
        keep_first = 0

    # 3. exclude_tool_types
    exclude_raw = args.get("exclude_tool_types")
    exclude_types, err = _validate_exclude_tool_types(exclude_raw)
    if err:
        errors.append(err)

    # 4. Zone overlap check
    # We don't know total message count here (middleware does), but we can
    # check the logical constraint: keep_first must be much less than
    # keep_last to leave room. If keep_first >= keep_last, warn.
    if keep_first > 0 and keep_first >= keep_last:
        warnings.append(
            f"keep_first_n_messages={keep_first} >= keep_last_n_messages={keep_last}. "
            "This leaves a very small or empty prune zone. "
            "Consider reducing keep_first_n_messages or increasing keep_last_n_messages."
        )

    # ─── If there are hard errors, return them all at once ────────────
    if errors:
        hint = (
            "Correct usage example: prune_tool_outputs(keep_last_n_messages=12, "
            'keep_first_n_messages=2, exclude_tool_types=["memory", "session_search"]). '
            "All parameters are optional. keep_last_n_messages defaults to 12."
        )
        return _error(
            f"{len(errors)} validation error(s): " + " | ".join(errors) + " | " + hint,
            validation_errors=errors,
            warnings=warnings,
            effective_values={
                "keep_last_n_messages": keep_last,
                "keep_first_n_messages": keep_first,
                "exclude_tool_types": exclude_types,
            },
        )

    # ─── Set the flag for the middleware ─────────────────────────────
    try:
        from .state import set_prune_requested
    except ImportError:
        from state import set_prune_requested

    set_prune_requested(
        keep_last=keep_last,
        keep_first=keep_first,
        exclude_tool_types=exclude_types,
    )

    logger.info(
        "prune_tool_outputs called: keep_last=%d, keep_first=%d, "
        "exclude=%s, errors=%d, warnings=%d",
        keep_last,
        keep_first,
        exclude_types,
        len(errors),
        len(warnings),
    )

    # ─── Build response ──────────────────────────────────────────────
    summary_parts = [f"keep_last_n_messages={keep_last}"]
    if keep_first:
        summary_parts.append(f"keep_first_n_messages={keep_first}")
    if exclude_types:
        summary_parts.append(f"exclude_tool_types={exclude_types}")

    response = {
        "pruned": True,
        "message": (
            "Tool output pruning triggered. On the next API call, tool results outside "
            f"the protected zone ({', '.join(summary_parts)}) will be replaced with "
            "compact 1-line summaries. The session store keeps originals — "
            "full content can be recovered there if needed."
        ),
        "keep_last_n_messages": keep_last,
        "keep_first_n_messages": keep_first,
        "exclude_tool_types": exclude_types,
    }

    if warnings:
        response["warnings"] = warnings

    return json.dumps(response)
