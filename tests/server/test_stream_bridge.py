"""Regression tests for streaming completed agent responses."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from openjarvis.agents._stubs import AgentResult  # noqa: E402
from openjarvis.core.events import EventBus  # noqa: E402
from openjarvis.core.types import ToolResult  # noqa: E402
from openjarvis.server.models import ChatCompletionRequest  # noqa: E402
from openjarvis.server.stream_bridge import AgentStreamBridge  # noqa: E402


def _streamed_content(events: list[str]) -> str:
    """Join assistant content from OpenAI-compatible data chunks."""
    content = []
    for event in events:
        if not event.startswith("data: {"):
            continue
        payload = json.loads(event.removeprefix("data: ").strip())
        choices = payload.get("choices")
        if choices and choices[0]["delta"].get("content"):
            content.append(choices[0]["delta"]["content"])
    return "".join(content)


def test_stream_replays_grounded_agent_result_without_second_inference():
    grounded_content = "My name is Jarvis. The tool reports 72 degrees."
    agent = MagicMock()
    agent._model = "configured-model"
    agent.run.return_value = AgentResult(
        content=grounded_content,
        tool_results=[
            ToolResult(tool_name="weather", content="72 degrees", success=True)
        ],
        metadata={"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
    )

    async def ungrounded_replay(*args, **kwargs):
        raise AssertionError("stream_full must not run after agent.run")
        yield  # pragma: no cover

    agent._engine.stream_full = ungrounded_replay
    request = ChatCompletionRequest(
        model="requested-model",
        messages=[{"role": "user", "content": "Who are you, and what's outside?"}],
        stream=True,
    )
    bridge = AgentStreamBridge(agent, EventBus(), request.model, request)

    async def collect_events() -> list[str]:
        return [event async for event in bridge.stream()]

    events = asyncio.run(collect_events())

    assert _streamed_content(events) == grounded_content
    assert any(event.startswith("event: tool_results\n") for event in events)
    agent.run.assert_called_once()
    assert agent._model == "configured-model"


def test_tool_call_start_serializes_arguments_for_sse_without_mutating_event():
    bridge = object.__new__(AgentStreamBridge)
    event_data = {
        "tool": "web_search",
        "arguments": {"query": "python"},
        "agent": "agent-1",
    }

    event = bridge._format_named_event("tool_call_start", event_data)
    payload = json.loads(event.split("data: ", 1)[1])

    assert payload["arguments"] == '{"query": "python"}'
    assert event_data["arguments"] == {"query": "python"}


def test_tool_call_start_preserves_already_serialized_arguments():
    bridge = object.__new__(AgentStreamBridge)

    event = bridge._format_named_event(
        "tool_call_start",
        {"tool": "web_search", "arguments": '{"query":"python"}'},
    )
    payload = json.loads(event.split("data: ", 1)[1])

    assert payload["arguments"] == '{"query":"python"}'


# --- Fail-closed delivery (regression) ------------------------------------

_SAMPLE = "sk-abcdefghij1234567890ABCD"


def _all_events(events: list[str]) -> str:
    return "\n".join(events)


def _bridge_with_result(content: str, tool_results=None, run_exc=None):
    agent = MagicMock()
    agent._model = "configured-model"
    if run_exc is not None:
        agent.run.side_effect = run_exc
    else:
        agent.run.return_value = AgentResult(
            content=content,
            tool_results=tool_results or [],
            metadata={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )
    request = ChatCompletionRequest(
        model="requested-model",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )
    return AgentStreamBridge(agent, EventBus(), request.model, request)


def test_named_event_tool_call_arguments_redacted():
    bridge = object.__new__(AgentStreamBridge)
    frame = bridge._format_named_event(
        "tool_call_start",
        {"tool": "search", "arguments": {"query": _SAMPLE, "x": 1}},
    )
    assert _SAMPLE not in frame
    assert "[REDACTED:openai_key]" in frame
    # tool_call_start serialises arguments to a JSON string; parse it back.
    payload = json.loads(frame.split("data: ", 1)[1])
    assert json.loads(payload["arguments"])["query"] == "[REDACTED:openai_key]"


def test_named_event_malformed_data_never_emits_raw():
    bridge = object.__new__(AgentStreamBridge)
    cyclic: dict = {"secret": _SAMPLE}
    cyclic["self"] = cyclic

    class _Bad:
        def __repr__(self):
            return f"leak {_SAMPLE}"

    frame = bridge._format_named_event(
        "tool_call_end", {"result": _Bad(), "cyclic": cyclic}
    )
    assert _SAMPLE not in frame
    # Still valid SSE / JSON.
    assert frame.startswith("event: tool_call_end\ndata: ")
    json.loads(frame.split("data: ", 1)[1])


def test_named_event_name_injection_sanitized():
    bridge = object.__new__(AgentStreamBridge)
    frame = bridge._format_named_event("evil\ndata: injected", {"a": 1})
    assert frame.startswith("event: event\n")
    assert "injected" not in frame


def test_tool_results_and_final_content_redacted_in_stream():
    bridge = _bridge_with_result(
        f"final {_SAMPLE} done",
        tool_results=[
            ToolResult(tool_name="tool", content=f"output {_SAMPLE}", success=True)
        ],
    )
    events = asyncio.run(_collect(bridge))
    assert _SAMPLE not in _all_events(events)
    assert "[REDACTED:openai_key]" in _all_events(events)
    assert _streamed_content(events) == "final [REDACTED:openai_key] done"


async def _collect(bridge):
    return [event async for event in bridge.stream()]


def test_error_chunk_never_embeds_exception_text():
    bridge = _bridge_with_result(
        "", run_exc=ValueError(f"400 upstream failure {_SAMPLE}")
    )
    events = asyncio.run(_collect(bridge))
    assert _SAMPLE not in _all_events(events)
    assert "400" not in _all_events(events)


def test_scanner_failure_falls_back_in_stream(monkeypatch):
    import openjarvis.security.scanner as scanner_mod

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("scanner down")

    monkeypatch.setattr(scanner_mod, "SecretScanner", _Boom)
    bridge = _bridge_with_result(f"final {_SAMPLE} done")
    events = asyncio.run(_collect(bridge))
    assert _SAMPLE not in _all_events(events)
    assert "[REDACTED:openai_key]" in _all_events(events)


def test_format_named_event_redacts_nested_tool_result():
    bridge = object.__new__(AgentStreamBridge)
    frame = bridge._format_named_event(
        "tool_call_end",
        {"tool": "x", "result": {"nested": [f"leak {_SAMPLE}"]}},
    )
    assert _SAMPLE not in frame
    assert "[REDACTED:openai_key]" in frame
