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

"""Shared test fixtures."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

import state  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_prune_state():
    """Keep the global prune-request flag isolated between tests."""
    state.get_and_clear_prune_request()
    yield
    state.get_and_clear_prune_request()
