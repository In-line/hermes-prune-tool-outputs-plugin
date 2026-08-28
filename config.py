"""Configuration for hermes-prune-tool-outputs plugin."""

import os


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


# -- Protection window ---
# Number of recent messages to always keep full (never prune).
# The model can override this per-call via keep_last_n_messages.
PRUNE_PROTECT_TAIL_COUNT = 12

# -- Logging ---
PRUNE_LOG_VERBOSE = _env_bool("PRUNE_TOOL_OUTPUTS_LOG_VERBOSE", False)
