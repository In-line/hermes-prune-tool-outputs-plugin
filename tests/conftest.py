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
