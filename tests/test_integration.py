"""Integration tests: tool handler -> state -> middleware end-to-end."""

import json

import middleware
from middleware import llm_request_middleware
from tool import handle_prune_tool_outputs


def _msg(role, content="", tool_calls=None, tool_call_id=None):
    msg = {"role": role, "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if tool_call_id:
        msg["tool_call_id"] = tool_call_id
    return msg


def _tool_call(cid, name="terminal", args="{}"):
    return {"id": cid, "function": {"name": name, "arguments": args}}


def _run(request):
    """Run the middleware and return its messages (asserting it modified)."""
    out = llm_request_middleware(request=request)
    assert out is not None, "middleware returned None"
    return out["request"]["messages"]


def _conversation():
    big = "x" * 1000
    return [
        _msg("system", "You are Hermes."),
        _msg("user", "run the tests"),
        _msg("assistant", "", tool_calls=[_tool_call("c1", "terminal", '{"command": "pytest"}')]),
        _msg("tool", big, tool_call_id="c1"),
        _msg("assistant", "tests passed, reading files"),
        _msg("assistant", "", tool_calls=[_tool_call("c2", "read_file", '{"path": "a.py"}')]),
        _msg("tool", big, tool_call_id="c2"),
        _msg("user", "ok"),
        _msg("user", "now summarize"),
        _msg("user", "and review"),
    ]


class TestEndToEnd:
    def test_full_flow(self):
        resp = json.loads(handle_prune_tool_outputs({"keep_last_n_messages": 2}))
        assert resp["pruned"] is True

        msgs = _run({"messages": _conversation()})

        # System instruction injected exactly once
        assert msgs[0]["content"].count("Prune Tool Outputs") == 1
        # Flag consumed after one middleware pass
        from state import get_and_clear_prune_request

        assert get_and_clear_prune_request()[0] is False
        # Both old tool outputs replaced (dedup pass + summary pass)
        assert msgs[3]["content"].startswith("[Duplicate tool output")
        assert msgs[6]["content"].startswith("[read_file]")
        assert "1,000 chars" in msgs[6]["content"]
        # Protected tail untouched
        assert msgs[9]["content"] == "and review"

    def test_instruction_injection_idempotent(self):
        request = {"messages": _conversation()}
        msgs1 = _run(request)
        assert "Prune Tool Outputs" in msgs1[0]["content"]
        # Second call: no further changes (no flag set)
        out2 = llm_request_middleware(request={"messages": msgs1})
        assert out2 is None

    def test_no_prune_without_tool_call(self):
        out = llm_request_middleware(request={"messages": _conversation()})
        assert out is not None
        msgs = out["request"]["messages"]
        # Only the system instruction is added; tool outputs untouched
        assert msgs[3]["content"] == "x" * 1000
        assert msgs[6]["content"] == "x" * 1000

    def test_prune_zone_boundaries(self):
        handle_prune_tool_outputs({"keep_last_n_messages": 2, "keep_first_n_messages": 1})
        msgs = _run({"messages": _conversation()})
        assert msgs[0]["content"].startswith("You are Hermes.")  # keep_first=1 zone
        assert msgs[3]["content"].startswith(("[Duplicate", "[terminal]"))
        assert msgs[6]["content"].startswith("[read_file]")

    def test_exclude_tool_types_end_to_end(self):
        handle_prune_tool_outputs({"exclude_tool_types": ["terminal", "read_file"]})
        msgs = _run({"messages": _conversation()})
        assert msgs[3]["content"] == "x" * 1000
        assert msgs[6]["content"] == "x" * 1000
        # Instruction still injected
        assert "Prune Tool Outputs" in msgs[0]["content"]

    def test_dedup_keeps_newest(self):
        big = "y" * 500
        msgs = [
            _msg("system", "s"),
            _msg("user", "u"),
            _msg("assistant", "", tool_calls=[_tool_call("c1", "fetch", '{"u": "1"}')]),
            _msg("tool", big, tool_call_id="c1"),
            _msg("user", "1"),
            _msg("user", "2"),
            _msg("assistant", "", tool_calls=[_tool_call("c2", "fetch", '{"u": "2"}')]),
            _msg("tool", big, tool_call_id="c2"),
            _msg("user", "3"),
            _msg("user", "4"),
        ]
        handle_prune_tool_outputs({"keep_last_n_messages": 2})
        got = _run({"messages": msgs})
        assert got[3]["content"].startswith("[Duplicate tool output")
        assert got[7]["content"].startswith("[fetch]")

    def test_short_conversation_noop(self):
        out = llm_request_middleware(
            request={"messages": [_msg("user", "hi"), _msg("assistant", "hello")]}
        )
        assert out is None

    def test_second_call_without_flag_is_noop(self):
        # Instruction injected on first call only; second call must be a no-op
        first = llm_request_middleware(request={"messages": _conversation()})
        assert first is not None
        second = llm_request_middleware(request=first["request"])
        assert second is None


class TestCacheStability:
    def test_instruction_is_deterministic(self):
        instruction = middleware._SYSTEM_INSTRUCTION
        assert "prune_tool_outputs" in instruction
        assert instruction.startswith("\n\n##")  # stable prefix structure
