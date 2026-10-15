"""Tests for the agentic-browser-bridge integration (secure profile)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from openjarvis.core.types import ToolResult
from openjarvis.mcp.browser_bridge import (
    BRIDGE_CONSEQUENTIAL_TOOLS,
    BRIDGE_DEFAULT_ALLOWED_ORIGINS,
    BRIDGE_DEFAULT_INCLUDE_TOOLS,
    BRIDGE_KNOWN_TOOLS,
    BRIDGE_SERVER_NAME,
    BridgePolicy,
    BridgeToolAdapter,
    apply_bridge_guard,
    bridge_server_entry,
    check_navigation_url,
    is_origin_allowed,
    requires_confirmation,
    resolve_bridge_path,
    secure_profile_tool_names,
)
from openjarvis.tools._stubs import BaseTool, ToolSpec


class _FakeTool(BaseTool):
    """Minimal BaseTool for guard tests; records whether it was called."""

    tool_id = "fake"

    def __init__(self, name: str) -> None:
        self._name = name
        self.calls: list[dict[str, Any]] = []

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name=self._name, description=f"Fake {self._name}")

    def execute(self, **params: Any) -> ToolResult:
        self.calls.append(params)
        return ToolResult(tool_name=self._name, content="ok", success=True)


# ---------------------------------------------------------------------------
# Entry shape
# ---------------------------------------------------------------------------


class TestBridgeServerEntry:
    def test_entry_shape(self, tmp_path):
        entry = bridge_server_entry(str(tmp_path))
        assert entry["name"] == BRIDGE_SERVER_NAME
        assert entry["command"] == "node"
        assert entry["args"] == [
            str(tmp_path / "dist" / "src" / "index.js"),
            "mcp",
            "--transport",
            "stdio",
        ]
        assert entry["include_tools"] == sorted(BRIDGE_DEFAULT_INCLUDE_TOOLS)
        assert entry["allowed_origins"] == list(BRIDGE_DEFAULT_ALLOWED_ORIGINS)

    def test_explicit_include_tools_and_origins(self, tmp_path):
        entry = bridge_server_entry(
            str(tmp_path),
            include_tools=["browser_snapshot"],
            allowed_origins=["http://127.0.0.1:8000"],
        )
        assert entry["include_tools"] == ["browser_snapshot"]
        assert entry["allowed_origins"] == ["http://127.0.0.1:8000"]

    def test_default_path_is_documented_checkout(self, monkeypatch):
        monkeypatch.delenv("OPENJARVIS_BRIDGE_PATH", raising=False)
        assert resolve_bridge_path().endswith("agentic-browser-bridge")

    def test_env_overrides_default_path(self, monkeypatch):
        monkeypatch.setenv("OPENJARVIS_BRIDGE_PATH", "/opt/bridge")
        assert resolve_bridge_path() == "/opt/bridge"

    def test_explicit_path_beats_env(self, monkeypatch):
        monkeypatch.setenv("OPENJARVIS_BRIDGE_PATH", "/opt/bridge")
        assert resolve_bridge_path("/srv/bridge") == "/srv/bridge"

    def test_known_tools_cover_consequential_plus_default(self):
        assert BRIDGE_CONSEQUENTIAL_TOOLS <= BRIDGE_KNOWN_TOOLS
        assert BRIDGE_DEFAULT_INCLUDE_TOOLS <= BRIDGE_KNOWN_TOOLS
        assert not (BRIDGE_CONSEQUENTIAL_TOOLS & BRIDGE_DEFAULT_INCLUDE_TOOLS)
        # Upload and tab-close are consequential-only (never in the default).
        assert "browser_upload" in BRIDGE_CONSEQUENTIAL_TOOLS
        assert "browser_close_tab" in BRIDGE_CONSEQUENTIAL_TOOLS


# ---------------------------------------------------------------------------
# Origin policy
# ---------------------------------------------------------------------------


class TestOriginPolicy:
    def test_loopback_and_example_allowed(self):
        assert is_origin_allowed(
            "http://127.0.0.1:8000/page", BRIDGE_DEFAULT_ALLOWED_ORIGINS
        )
        assert is_origin_allowed(
            "http://localhost/page", BRIDGE_DEFAULT_ALLOWED_ORIGINS
        )
        assert is_origin_allowed("https://example.com/", BRIDGE_DEFAULT_ALLOWED_ORIGINS)

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.com/",
            "https://example.com.evil.com/",
            "http://example.com/",  # wrong scheme for the example.com entry
            "https://127.0.0.1/",  # wrong scheme for the loopback entries
            "file:///etc/passwd",
            "data:text/html,<h1>x</h1>",
            "javascript:alert(1)",
            "http://user:pass@127.0.0.1/",
            "http://127.0.0.1.evil.com/",
            "",
            "not-a-url",
        ],
    )
    def test_disallowed_urls(self, url):
        assert not is_origin_allowed(url, BRIDGE_DEFAULT_ALLOWED_ORIGINS)

    def test_entry_port_must_match_when_set(self):
        allowed = ["http://127.0.0.1:8000"]
        assert is_origin_allowed("http://127.0.0.1:8000/", allowed)
        assert not is_origin_allowed("http://127.0.0.1:9000/", allowed)

    def test_path_prefix_entries(self):
        allowed = ["https://example.com/docs"]
        assert is_origin_allowed("https://example.com/docs/x", allowed)
        assert not is_origin_allowed("https://example.com/other", allowed)

    def test_check_navigation_url_message(self):
        assert (
            check_navigation_url("https://example.com/", BRIDGE_DEFAULT_ALLOWED_ORIGINS)
            is None
        )
        assert (
            check_navigation_url("file:///etc/passwd", BRIDGE_DEFAULT_ALLOWED_ORIGINS)
            is not None
        )


# ---------------------------------------------------------------------------
# Policy + guard
# ---------------------------------------------------------------------------


class TestBridgePolicy:
    def test_default_policy_is_default_allowlist(self):
        policy = BridgePolicy.from_config({})
        assert policy.include_tools == frozenset(BRIDGE_DEFAULT_INCLUDE_TOOLS)
        assert policy.confirm is None

    def test_explicit_include_admits_consequential(self):
        policy = BridgePolicy.from_config(
            {"include_tools": ["browser_click"]},
        )
        assert "browser_click" in policy.include_tools

    def test_unknown_explicit_names_never_admitted(self):
        policy = BridgePolicy.from_config({"include_tools": ["browser_evil"]})
        assert "browser_evil" not in policy.include_tools

    def test_allowed_origins_from_config(self):
        policy = BridgePolicy.from_config(
            {"allowed_origins": ["https://example.com"]},
        )
        assert policy.allowed_origins == ("https://example.com",)


class TestBridgeToolAdapter:
    def test_read_only_passes_through(self):
        tool = _FakeTool("browser_snapshot")
        guarded = BridgeToolAdapter(tool, BridgePolicy.from_config({}))
        result = guarded.execute()
        assert result.success
        assert tool.calls == [{}]

    def test_consequential_refused_without_confirmer(self):
        tool = _FakeTool("browser_click")
        policy = BridgePolicy.from_config({"include_tools": ["browser_click"]})
        guarded = BridgeToolAdapter(tool, policy)
        result = guarded.execute(ref="e1")
        assert not result.success
        assert "confirmation" in result.content
        assert tool.calls == []

    def test_consequential_allowed_with_confirmer(self):
        tool = _FakeTool("browser_click")
        policy = BridgePolicy(
            include_tools=frozenset(BRIDGE_DEFAULT_INCLUDE_TOOLS | {"browser_click"}),
            confirm=lambda name, params: name == "browser_click",
        )
        guarded = BridgeToolAdapter(tool, policy)
        result = guarded.execute(ref="e1")
        assert result.success
        assert tool.calls == [{"ref": "e1"}]

    def test_consequential_denied_by_confirmer(self):
        tool = _FakeTool("browser_click")
        policy = BridgePolicy(
            include_tools=frozenset(BRIDGE_DEFAULT_INCLUDE_TOOLS | {"browser_click"}),
            confirm=lambda name, params: False,
        )
        guarded = BridgeToolAdapter(tool, policy)
        result = guarded.execute(ref="e1")
        assert not result.success
        assert "denied" in result.content
        assert tool.calls == []

    def test_not_in_allowlist_refused(self):
        tool = _FakeTool("browser_upload")
        guarded = BridgeToolAdapter(tool, BridgePolicy.from_config({}))
        result = guarded.execute(ref="e1", filePath="/tmp/x.txt")
        assert not result.success
        assert "allowlist" in result.content
        assert tool.calls == []

    def test_unknown_tool_refused(self):
        tool = _FakeTool("browser_evil")
        guarded = BridgeToolAdapter(tool, BridgePolicy.from_config({}))
        result = guarded.execute()
        assert not result.success
        assert tool.calls == []

    def test_navigate_to_disallowed_origin_refused_despite_confirmer(self):
        tool = _FakeTool("browser_navigate")
        policy = BridgePolicy(
            include_tools=frozenset(
                BRIDGE_DEFAULT_INCLUDE_TOOLS | {"browser_navigate"}
            ),
            confirm=lambda name, params: True,
        )
        guarded = BridgeToolAdapter(tool, policy)
        result = guarded.execute(url="https://evil.example.com/")
        assert not result.success
        assert "allowed_origins" in result.content
        assert tool.calls == []

    def test_navigate_to_allowed_origin_with_confirmer(self):
        tool = _FakeTool("browser_navigate")
        policy = BridgePolicy(
            include_tools=frozenset(
                BRIDGE_DEFAULT_INCLUDE_TOOLS | {"browser_navigate"}
            ),
            confirm=lambda name, params: True,
        )
        guarded = BridgeToolAdapter(tool, policy)
        result = guarded.execute(url="https://example.com/")
        assert result.success
        assert tool.calls == [{"url": "https://example.com/"}]

    def test_spec_delegates_to_inner_tool(self):
        tool = _FakeTool("browser_snapshot")
        guarded = BridgeToolAdapter(tool, BridgePolicy.from_config({}))
        assert guarded.spec.name == "browser_snapshot"


class TestApplyBridgeGuard:
    def test_drops_non_allowlisted_and_unknown(self):
        tools = [
            _FakeTool("browser_snapshot"),
            _FakeTool("browser_click"),
            _FakeTool("browser_evil"),
        ]
        guarded = apply_bridge_guard(tools, cfg={})
        assert [t.spec.name for t in guarded] == ["browser_snapshot"]
        assert all(isinstance(t, BridgeToolAdapter) for t in guarded)

    def test_explicit_opt_in_keeps_consequential_wrapped(self):
        tools = [_FakeTool("browser_click")]
        guarded = apply_bridge_guard(tools, cfg={"include_tools": ["browser_click"]})
        assert len(guarded) == 1
        # Still refused at call time: no confirmer on a config path.
        assert not guarded[0].execute(ref="e1").success

    def test_requires_confirmation(self):
        assert requires_confirmation("browser_click")
        assert requires_confirmation("browser_navigate")
        assert not requires_confirmation("browser_snapshot")
        assert not requires_confirmation("browser_back")


# ---------------------------------------------------------------------------
# Secure profile: native browser tools
# ---------------------------------------------------------------------------


class TestSecureProfileToolNames:
    def test_native_browser_tools_off_by_default(self):
        from openjarvis.agents.tool_resolver import BROWSER_SUB_TOOLS

        names = ["calculator", *BROWSER_SUB_TOOLS]
        assert secure_profile_tool_names(names) == ["calculator"]

    def test_explicit_opt_in_restores_named_tool_only(self):
        names = ["browser_navigate", "browser_click", "calculator"]
        assert secure_profile_tool_names(
            names, browser_opt_in=["browser_navigate"]
        ) == ["browser_navigate", "calculator"]

    def test_non_browser_names_unaffected(self):
        assert secure_profile_tool_names(["think", "llm"]) == ["think", "llm"]


class TestMCPServerNativeBrowserDefault:
    @staticmethod
    def _reregister_browser_tools() -> None:
        # conftest clears ToolRegistry before each test, and the browser
        # modules are already in sys.modules, so their @register
        # decorators won't re-run on a plain import — reload them.
        import importlib
        import sys

        import openjarvis.tools.browser  # noqa: F401
        import openjarvis.tools.browser_axtree  # noqa: F401

        for mod in ("openjarvis.tools.browser", "openjarvis.tools.browser_axtree"):
            importlib.reload(sys.modules[mod])

    def test_auto_discovery_excludes_native_browser_tools(self):
        self._reregister_browser_tools()

        from openjarvis.mcp.server import MCPServer

        server = MCPServer()
        names = {t.spec.name for t in server.get_tools()}
        assert "browser_navigate" not in names
        assert "browser_axtree" not in names
        assert "calculator" in names

    def test_auto_discovery_opt_in_includes_native_browser_tools(self):
        self._reregister_browser_tools()

        from openjarvis.mcp.server import MCPServer

        server = MCPServer(include_browser_tools=True)
        names = {t.spec.name for t in server.get_tools()}
        assert "browser_navigate" in names


# ---------------------------------------------------------------------------
# Builder discovery applies the guard for the bridge server
# ---------------------------------------------------------------------------


def _make_mock_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.spec = ToolSpec(name=name, description=f"Mock {name}")
    return tool


@pytest.fixture
def builder():
    from openjarvis.system import SystemBuilder

    def _minimal_init(self):
        self._mcp_clients = []
        self._tool_names = None

    with patch.object(SystemBuilder, "__init__", _minimal_init):
        instance = SystemBuilder.__new__(SystemBuilder)
        instance.__init__()
        return instance


class TestBuilderBridgeGuard:
    @patch("openjarvis.tools.mcp_adapter.MCPToolProvider")
    @patch("openjarvis.mcp.client.MCPClient")
    @patch("openjarvis.mcp.transport.StdioTransport")
    def test_bridge_config_tool_list_opts_in(
        self, mock_transport_cls, mock_client_cls, mock_provider_cls, builder
    ):
        from types import SimpleNamespace

        mock_provider_cls.return_value.discover.return_value = [
            _make_mock_tool("browser_snapshot"),
            _make_mock_tool("browser_click"),
        ]
        builder._config = SimpleNamespace(
            tools=SimpleNamespace(enabled="browser_click"),
            agent=SimpleNamespace(tools=""),
        )
        cfg = {
            "name": "agentic-browser-bridge",
            "command": "node",
            "args": ["server.js"],
        }
        result = builder._discover_external_mcp(cfg)
        # browser_click is explicitly named in config → kept (wrapped);
        # it still refuses at call time without a confirmer.
        assert [t.spec.name for t in result] == [
            "browser_snapshot",
            "browser_click",
        ]
        assert not result[1].execute(ref="e1").success

    @patch("openjarvis.tools.mcp_adapter.MCPToolProvider")
    @patch("openjarvis.mcp.client.MCPClient")
    @patch("openjarvis.mcp.transport.StdioTransport")
    def test_bridge_server_gets_guard(
        self, mock_transport_cls, mock_client_cls, mock_provider_cls, builder
    ):
        mock_provider_cls.return_value.discover.return_value = [
            _make_mock_tool("browser_snapshot"),
            _make_mock_tool("browser_click"),
            _make_mock_tool("browser_evil"),
        ]
        cfg = {
            "name": "agentic-browser-bridge",
            "command": "node",
            "args": ["server.js"],
        }
        result = builder._discover_external_mcp(cfg)
        # Only the default-allowlisted tool survives, wrapped by the guard.
        assert [t.spec.name for t in result] == ["browser_snapshot"]
        assert isinstance(result[0], BridgeToolAdapter)

    @patch("openjarvis.tools.mcp_adapter.MCPToolProvider")
    @patch("openjarvis.mcp.client.MCPClient")
    @patch("openjarvis.mcp.transport.StdioTransport")
    def test_non_bridge_server_untouched(
        self, mock_transport_cls, mock_client_cls, mock_provider_cls, builder
    ):
        mock_provider_cls.return_value.discover.return_value = [
            _make_mock_tool("some_tool"),
        ]
        cfg = {"name": "other", "command": "node", "args": ["server.js"]}
        result = builder._discover_external_mcp(cfg)
        assert [t.spec.name for t in result] == ["some_tool"]
        assert not isinstance(result[0], BridgeToolAdapter)
