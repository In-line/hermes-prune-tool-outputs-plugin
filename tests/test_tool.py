"""Unit tests for tool.py (validation) and state.py."""

import json

import pytest

from state import get_and_clear_prune_request, set_prune_requested
from tool import TOOL_SCHEMA, handle_prune_tool_outputs


class TestValidation:
    def test_defaults_applied(self):
        resp = json.loads(handle_prune_tool_outputs({}))
        assert resp["pruned"] is True
        assert resp["keep_last_n_messages"] == 12
        assert resp["keep_first_n_messages"] == 0
        assert resp["exclude_tool_types"] == []
        # Flag must be set for the middleware
        was, kl, kf, et = get_and_clear_prune_request()
        assert was is True and kl == 12 and kf == 0 and et == []

    def test_valid_explicit_values(self):
        resp = json.loads(
            handle_prune_tool_outputs(
                {
                    "keep_last_n_messages": 5,
                    "keep_first_n_messages": 2,
                    "exclude_tool_types": ["memory", "memory", "session_search"],
                }
            )
        )
        assert resp["pruned"] is True
        assert resp["exclude_tool_types"] == ["memory", "session_search"]

    @pytest.mark.parametrize("bad", [1, "abc", True, 501, 0])
    def test_invalid_keep_last(self, bad):
        resp = json.loads(handle_prune_tool_outputs({"keep_last_n_messages": bad}))
        assert resp["error"] is True and resp["pruned"] is False
        assert "keep_last_n_messages" in resp["message"]

    @pytest.mark.parametrize("bad", [-1, 101, "x", True])
    def test_invalid_keep_first(self, bad):
        resp = json.loads(handle_prune_tool_outputs({"keep_first_n_messages": bad}))
        assert resp["error"] is True and resp["pruned"] is False

    def test_invalid_exclude_type(self):
        resp = json.loads(handle_prune_tool_outputs({"exclude_tool_types": ["ok", {"bad": 1}]}))
        assert resp["error"] is True
        assert resp["effective_values"]["exclude_tool_types"] == ["ok"]

    def test_all_errors_aggregated(self):
        resp = json.loads(
            handle_prune_tool_outputs({"keep_last_n_messages": 1, "keep_first_n_messages": -5})
        )
        assert "2 validation error(s)" in resp["message"]

    def test_deprecated_keep_recent_accepted_with_warning(self):
        resp = json.loads(handle_prune_tool_outputs({"keep_recent": 6}))
        assert resp["keep_last_n_messages"] == 6
        assert any("deprecated" in w for w in resp["warnings"])

    def test_schema_shape(self):
        assert TOOL_SCHEMA["name"] == "prune_tool_outputs"
        assert TOOL_SCHEMA["parameters"]["type"] == "object"


class TestState:
    def test_set_and_clear(self):
        set_prune_requested(keep_last=7, keep_first=1, exclude_tool_types=["a"])
        was, kl, kf, et = get_and_clear_prune_request()
        assert (was, kl, kf, et) == (True, 7, 1, ["a"])
        # Cleared after read
        assert get_and_clear_prune_request() == (False, None, 0, [])

    def test_initial_state(self):
        assert get_and_clear_prune_request() == (False, None, 0, [])
