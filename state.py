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

"""Shared state between tool handler and middleware.

The tool handler sets a prune request flag; the llm_request middleware
reads and clears it on the next API call.
"""

import threading

_lock = threading.Lock()
_prune_requested = False
_keep_last: int | None = None
_keep_first: int = 0
_exclude_tool_types: list[str] = []


def set_prune_requested(
    keep_last: int | None = None,
    keep_first: int = 0,
    exclude_tool_types: list[str] | None = None,
) -> None:
    """Set the prune-requested flag. Called by the tool handler."""
    global _prune_requested, _keep_last, _keep_first, _exclude_tool_types
    with _lock:
        _prune_requested = True
        _keep_last = keep_last
        _keep_first = keep_first
        _exclude_tool_types = exclude_tool_types or []


def get_and_clear_prune_request() -> tuple[bool, int | None, int, list[str]]:
    """Atomically read and clear the prune-requested flag.

    Returns (was_requested, keep_last, keep_first, exclude_tool_types).
    Called by the llm_request middleware.
    """
    global _prune_requested, _keep_last, _keep_first, _exclude_tool_types
    with _lock:
        was = _prune_requested
        kl = _keep_last
        kf = _keep_first
        et = list(_exclude_tool_types)
        _prune_requested = False
        _keep_last = None
        _keep_first = 0
        _exclude_tool_types = []
    return was, kl, kf, et
