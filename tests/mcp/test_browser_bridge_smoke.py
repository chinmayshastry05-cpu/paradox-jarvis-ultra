"""Real stdio smoke test: handshake + tools/list against the bridge.

This test talks to the actual ``agentic-browser-bridge`` MCP server
(``node <path>/dist/src/index.js mcp --transport stdio``) — it performs
only ``initialize`` + ``tools/list`` and never calls a tool, so it
navigates nowhere and touches no page.

It is skipped (NOT faked) when the bridge checkout or ``node`` is not
available in this environment. The path comes from
``OPENJARVIS_BRIDGE_PATH`` or the documented default
``~/agentic-browser-bridge``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from openjarvis.mcp.browser_bridge import (
    BRIDGE_DEFAULT_INCLUDE_TOOLS,
    BRIDGE_SERVER_NAME,
    bridge_server_entry,
    resolve_bridge_path,
)
from openjarvis.mcp.client import MCPClient
from openjarvis.mcp.transport import StdioTransport


def _bridge_entry_path() -> Path:
    entry = bridge_server_entry()
    return Path(entry["args"][0])


@pytest.mark.slow
def test_bridge_stdio_handshake_and_tool_list():
    entry = bridge_server_entry()
    entry_path = Path(entry["args"][0])
    if not entry_path.is_file():
        pytest.skip(
            f"bridge entry not found at {entry_path} "
            f"(checkout {resolve_bridge_path()} missing or unbuilt) — "
            "smoke test UNTESTED in this environment"
        )
    if shutil.which("node") is None:
        pytest.skip("node not available — smoke test UNTESTED")

    assert entry["name"] == BRIDGE_SERVER_NAME
    assert entry["command"] == "node"

    transport = StdioTransport(
        command=[entry["command"]] + entry["args"],
        response_timeout=60.0,
    )
    client = MCPClient(transport)
    try:
        info = client.initialize()
        assert info["serverInfo"]["name"] == "agentic-browser-bridge"
        tools = client.list_tools()
        names = {t.name for t in tools}
        # The bridge must expose at least the secure-profile default set.
        missing = set(BRIDGE_DEFAULT_INCLUDE_TOOLS) - names
        assert not missing, f"bridge missing default tools: {sorted(missing)}"
        # Pin the allowlist to the real bridge: a new/renamed bridge tool
        # must get an explicit allowlist review, never silent admission.
        from openjarvis.mcp.browser_bridge import BRIDGE_KNOWN_TOOLS

        assert names == set(BRIDGE_KNOWN_TOOLS), (
            f"bridge tool set drifted from BRIDGE_KNOWN_TOOLS: "
            f"extra={sorted(names - set(BRIDGE_KNOWN_TOOLS))}, "
            f"missing={sorted(set(BRIDGE_KNOWN_TOOLS) - names)}"
        )
    finally:
        client.close()
