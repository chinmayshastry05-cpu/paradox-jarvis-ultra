"""Agentic Browser Bridge integration — MCP stdio server + secure profile.

The bridge is the ``agentic-browser-bridge`` project
(https://github.com/chinmayshastry05-cpu/agentic-browser-bridge): a
local-first MCP bridge that lets an agent observe and act inside a real
browser session. OpenJarvis talks to it as an *external* MCP server over
stdio — it is never imported, and no bridge code runs in-process.

Entry shape (what goes in ``tools.mcp.servers``)::

    {
        "name": "agentic-browser-bridge",
        "command": "node",
        "args": ["<bridge-path>/dist/src/index.js", "mcp",
                 "--transport", "stdio"],
        "include_tools": ["browser_snapshot", ...],  # allowlist, see below
        "allowed_origins": ["http://127.0.0.1", ...],  # navigation allowlist
    }

Use :func:`bridge_server_entry` to build that dict. ``<bridge-path>`` is
configurable: pass ``bridge_path`` explicitly, set the
``OPENJARVIS_BRIDGE_PATH`` environment variable, or accept the documented
default ``~/agentic-browser-bridge`` (a checkout of the repo above).
No machine-specific path is hardcoded as the only option.

Secure profile
--------------
* **Allowlist.** Only tools in :data:`BRIDGE_DEFAULT_INCLUDE_TOOLS`
  (read-only + reversible tools) load by default. Anything else must be
  listed explicitly (``include_tools`` in config, or the caller's tool
  list) — and unknown tool names are dropped, never passed through.
* **Per-origin.** Navigation (``browser_navigate`` / ``browser_open_tab``)
  is refused unless the target URL's origin is in ``allowed_origins``.
  Default: loopback + ``https://example.com`` only. Non-HTTP(S) schemes
  (``file:``, ``data:``, ...) and URLs with embedded credentials are
  always refused, even if the origin matches.
* **Confirmation.** :data:`BRIDGE_CONSEQUENTIAL_TOOLS` (click, type,
  navigate, ...) need an operator confirmation callback. With no
  confirmer configured they are refused — fail-closed. Config files
  cannot carry a callback, so consequential tools stay refused on
  config-driven paths until a caller supplies one programmatically.
* **No fallback.** A refused bridge call returns a failed
  ``ToolResult``. It never falls back to a shell command or to the
  native browser tools.
* **Native browser tools off.** The pre-existing native tools
  (``browser_navigate``, ``browser_click``, ...) are redundant with the
  bridge and have no confirmation/origin gate. They stay off by default
  (see :func:`secure_profile_tool_names` and the ``MCPServer``
  ``include_browser_tools`` opt-in) and are enabled only by explicitly
  naming them. The bridge never enables authenticated access to private
  services: the bridge itself holds no credentials and refuses login
  walls.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Collection, Iterable, Optional
from urllib.parse import urlparse

from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

BRIDGE_SERVER_NAME = "agentic-browser-bridge"
BRIDGE_REPO_URL = "https://github.com/chinmayshastry05-cpu/agentic-browser-bridge"
BRIDGE_PATH_ENV = "OPENJARVIS_BRIDGE_PATH"
BRIDGE_DEFAULT_DIR = "~/agentic-browser-bridge"

# Tools the bridge MCP server exposes (src/tools.ts in the bridge repo).
# Kept as data, not discovered, so an unknown/future tool name can never
# slip through the guard by accident.
BRIDGE_READ_ONLY_TOOLS = frozenset(
    {
        "browser_snapshot",
        "browser_screenshot",
        "browser_get_text",
        "browser_page_info",
        "browser_tabs",
        "browser_frames",
        "browser_frame_snapshot",
        "browser_status",
        "browser_downloads",
        "browser_wait_for_download",
        "browser_verify",
    }
)
BRIDGE_MILD_TOOLS = frozenset(
    {
        # Reversible state changes that stay on the current page/origin.
        "browser_hover",
        "browser_focus",
        "browser_scroll_into_view",
        "browser_scroll",
        "browser_wait_for",
        "browser_back",
        "browser_forward",
        "browser_reload",
        "browser_switch_tab",
    }
)
BRIDGE_CONSEQUENTIAL_TOOLS = frozenset(
    {
        # Change page content, submit input, open/close tabs, or upload files.
        "browser_navigate",
        "browser_click",
        "browser_click_at",
        "browser_double_click",
        "browser_type",
        "browser_clear",
        "browser_press_key",
        "browser_select_option",
        "browser_check",
        "browser_open_tab",
        "browser_close_tab",
        "browser_upload",
    }
)
BRIDGE_KNOWN_TOOLS = (
    BRIDGE_READ_ONLY_TOOLS | BRIDGE_MILD_TOOLS | BRIDGE_CONSEQUENTIAL_TOOLS
)
#: Default allowlist: read-only + reversible tools. Uploads, tab closing
#: and all other consequential tools need explicit opt-in + confirmation.
BRIDGE_DEFAULT_INCLUDE_TOOLS = BRIDGE_READ_ONLY_TOOLS | BRIDGE_MILD_TOOLS

#: Tools that take a ``url`` argument and therefore enter a new origin.
BRIDGE_NAVIGATION_TOOLS = frozenset({"browser_navigate", "browser_open_tab"})

#: Default navigation allowlist: local fixtures + one harmless public page.
BRIDGE_DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1",
    "http://localhost",
    "https://example.com",
)


def resolve_bridge_path(explicit: Optional[str] = None) -> str:
    """Resolve the bridge checkout dir: explicit > env > documented default."""
    raw = explicit or os.environ.get(BRIDGE_PATH_ENV) or BRIDGE_DEFAULT_DIR
    return str(Path(raw).expanduser())


def bridge_server_entry(
    bridge_path: Optional[str] = None,
    *,
    include_tools: Optional[Iterable[str]] = None,
    allowed_origins: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """Build the MCP server config entry for the bridge (stdio transport).

    The bridge runs as ``node <path>/dist/src/index.js mcp --transport
    stdio``. ``include_tools`` defaults to the secure allowlist
    (:data:`BRIDGE_DEFAULT_INCLUDE_TOOLS`); ``allowed_origins`` defaults
    to :data:`BRIDGE_DEFAULT_ALLOWED_ORIGINS`.
    """
    resolved = resolve_bridge_path(bridge_path)
    entry_path = str(Path(resolved) / "dist" / "src" / "index.js")
    return {
        "name": BRIDGE_SERVER_NAME,
        "command": "node",
        "args": [entry_path, "mcp", "--transport", "stdio"],
        "include_tools": sorted(
            include_tools if include_tools is not None else BRIDGE_DEFAULT_INCLUDE_TOOLS
        ),
        "allowed_origins": list(
            allowed_origins
            if allowed_origins is not None
            else BRIDGE_DEFAULT_ALLOWED_ORIGINS
        ),
    }


def _split_origin(entry: str) -> tuple[str, str, Optional[int], str]:
    """Split an origin entry into (scheme, host, port-or-None, path-prefix)."""
    parsed = urlparse(entry)
    host = (parsed.hostname or "").lower()
    return (parsed.scheme.lower(), host, parsed.port, parsed.path or "")


def is_origin_allowed(url: str, allowed_origins: Collection[str]) -> bool:
    """True iff *url* is http(s), credential-free, and origin-listed."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    port = parsed.port
    path = parsed.path or "/"
    for entry in allowed_origins:
        scheme, e_host, e_port, e_path = _split_origin(entry)
        if scheme != parsed.scheme.lower() or e_host != host:
            continue
        if e_port is not None and e_port != port:
            continue
        if e_path and e_path != "/" and not path.startswith(e_path):
            continue
        return True
    return False


def check_navigation_url(url: Any, allowed_origins: Collection[str]) -> Optional[str]:
    """Return an error string if *url* must not be navigated to, else None."""
    if not isinstance(url, str) or not url:
        return "navigation requires a non-empty URL string"
    if not is_origin_allowed(url, allowed_origins):
        return (
            f"navigation to {url!r} is not in the bridge allowed_origins "
            f"({sorted(allowed_origins)})"
        )
    return None


def requires_confirmation(tool_name: str) -> bool:
    """True iff calling *tool_name* needs operator confirmation."""
    return tool_name in BRIDGE_CONSEQUENTIAL_TOOLS


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

#: Confirm callback: (tool_name, params) -> True to allow the call.
ConfirmCallback = Callable[[str, dict[str, Any]], bool]


@dataclass(frozen=True)
class BridgePolicy:
    """Enforcement policy for one bridge server."""

    include_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(BRIDGE_DEFAULT_INCLUDE_TOOLS)
    )
    allowed_origins: tuple[str, ...] = BRIDGE_DEFAULT_ALLOWED_ORIGINS
    confirm: Optional[ConfirmCallback] = None

    @classmethod
    def from_config(
        cls,
        cfg: Optional[dict[str, Any]] = None,
        *,
        explicit_tools: Optional[Collection[str]] = None,
    ) -> "BridgePolicy":
        """Build a policy from a server-config dict + caller opt-ins.

        The effective allowlist is the secure default plus any *known*
        bridge tools the operator explicitly listed (in the server
        entry's ``include_tools`` or the caller's tool list). Unknown
        names are never admitted.
        """
        cfg = cfg or {}
        explicit = set(explicit_tools or ())
        cfg_tools = cfg.get("include_tools")
        if isinstance(cfg_tools, (list, tuple, set)):
            explicit.update(cfg_tools)
        allowed = set(BRIDGE_DEFAULT_INCLUDE_TOOLS)
        allowed.update(t for t in explicit if t in BRIDGE_KNOWN_TOOLS)
        origins = cfg.get("allowed_origins")
        if isinstance(origins, (list, tuple)):
            origin_tuple = tuple(str(o) for o in origins)
        else:
            origin_tuple = BRIDGE_DEFAULT_ALLOWED_ORIGINS
        return cls(
            include_tools=frozenset(allowed),
            allowed_origins=origin_tuple,
        )


class BridgeToolAdapter(BaseTool):
    """Per-call guard around one discovered bridge tool.

    Enforces the allowlist, the origin policy (navigation tools), and
    the confirmation gate before delegating to the wrapped tool.
    Refusals are failed ``ToolResult``s, never exceptions and never a
    fallback to another tool.
    """

    tool_id = "bridge_guarded"

    def __init__(self, inner: BaseTool, policy: BridgePolicy) -> None:
        self._inner = inner
        self._policy = policy

    @property
    def spec(self):  # type: ignore[override]
        return self._inner.spec

    def _refuse(self, reason: str) -> ToolResult:
        return ToolResult(
            tool_name=self._inner.spec.name,
            content=f"Bridge tool refused: {reason}",
            success=False,
        )

    def execute(self, **params: Any) -> ToolResult:
        name = self._inner.spec.name
        if name not in BRIDGE_KNOWN_TOOLS:
            return self._refuse(
                f"unknown bridge tool {name!r} — not in the known tool set"
            )
        if name not in self._policy.include_tools:
            return self._refuse(
                f"{name!r} is not in the bridge allowlist; "
                "add it to include_tools explicitly to opt in"
            )
        if name in BRIDGE_NAVIGATION_TOOLS and params.get("url"):
            error = check_navigation_url(
                params.get("url"), self._policy.allowed_origins
            )
            if error is not None:
                return self._refuse(error)
        if requires_confirmation(name):
            if self._policy.confirm is None:
                return self._refuse(
                    f"{name!r} is consequential and needs operator "
                    "confirmation; no confirmer is configured"
                )
            try:
                allowed = bool(self._policy.confirm(name, dict(params)))
            except Exception as exc:
                return self._refuse(f"confirmation callback failed: {exc}")
            if not allowed:
                return self._refuse(f"operator confirmation denied for {name!r}")
        return self._inner.execute(**params)


def apply_bridge_guard(
    tools: Iterable[BaseTool],
    *,
    cfg: Optional[dict[str, Any]] = None,
    explicit_tools: Optional[Collection[str]] = None,
    policy: Optional[BridgePolicy] = None,
) -> list[BaseTool]:
    """Wrap discovered bridge tools with the secure-profile guard.

    Tools outside the effective allowlist (or with unknown names) are
    dropped with a warning; the rest are wrapped so every call is
    checked against the origin policy and the confirmation gate.
    """
    effective = policy or BridgePolicy.from_config(cfg, explicit_tools=explicit_tools)
    guarded: list[BaseTool] = []
    for tool in tools:
        name = tool.spec.name
        if name not in effective.include_tools or name not in BRIDGE_KNOWN_TOOLS:
            logger.warning("Dropping bridge tool %r: not in the secure allowlist", name)
            continue
        guarded.append(BridgeToolAdapter(tool, effective))
    return guarded


def secure_profile_tool_names(
    names: Iterable[str],
    *,
    browser_opt_in: Collection[str] = (),
) -> list[str]:
    """Drop native browser tools unless explicitly opted in.

    The native ``browser_*`` tools (see ``BROWSER_SUB_TOOLS`` in
    ``openjarvis.agents.tool_resolver``) are redundant with the bridge
    and have no confirmation/origin gate, so the secure profile keeps
    them off. Pass a tool name in ``browser_opt_in`` to enable exactly
    that tool. Non-browser names pass through unchanged.
    """
    # Local import: tool_resolver is heavy and browser_bridge must stay
    # importable from the MCP loader without pulling in agent machinery.
    from openjarvis.agents.tool_resolver import BROWSER_SUB_TOOLS

    native = set(BROWSER_SUB_TOOLS)
    opted_in = set(browser_opt_in)
    return [n for n in names if n not in native or n in opted_in]


__all__ = [
    "BRIDGE_SERVER_NAME",
    "BRIDGE_REPO_URL",
    "BRIDGE_PATH_ENV",
    "BRIDGE_DEFAULT_DIR",
    "BRIDGE_READ_ONLY_TOOLS",
    "BRIDGE_MILD_TOOLS",
    "BRIDGE_CONSEQUENTIAL_TOOLS",
    "BRIDGE_KNOWN_TOOLS",
    "BRIDGE_DEFAULT_INCLUDE_TOOLS",
    "BRIDGE_NAVIGATION_TOOLS",
    "BRIDGE_DEFAULT_ALLOWED_ORIGINS",
    "BridgePolicy",
    "BridgeToolAdapter",
    "apply_bridge_guard",
    "bridge_server_entry",
    "check_navigation_url",
    "is_origin_allowed",
    "requires_confirmation",
    "resolve_bridge_path",
    "secure_profile_tool_names",
]
