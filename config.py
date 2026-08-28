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
