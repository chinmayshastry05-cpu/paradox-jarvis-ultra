"""Single-use, argument-bound tool approvals.

This is the central confirmation store shared by every tool-execution
entry point (CLI, server, desktop-via-server, MCP). A granted approval is
bound to one exact tool name and one exact set of arguments, expires, can
be revoked, and is consumed on first use. Any reuse, argument tampering,
expiry, or revocation makes the approval reject the call.

There is intentionally no "approve everything" / "always allow" mode:
a blanket approval cannot be bound to exact arguments, so it cannot exist
here. Callers that need a human decision must obtain one per action.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

_DEFAULT_TTL_SECONDS = 300
_MAX_TTL_SECONDS = 3600


def canonical_arguments(arguments: Dict[str, Any]) -> str:
    """Canonical JSON for *arguments* (sorted keys, no whitespace).

    Raises :class:`ValueError` if *arguments* is not a JSON-serializable
    mapping. Canonical form is what approvals bind to: two argument sets
    with the same canonical form are the same action.
    """
    if not isinstance(arguments, dict):
        raise ValueError("approval arguments must be a JSON object")
    try:
        return json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"approval arguments are not JSON-serializable: {exc}"
        ) from exc


def _fingerprint(arguments: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_arguments(arguments).encode("utf-8")).hexdigest()


@dataclass
class Approval:
    """One granted approval. In-memory only; never persisted to disk."""

    token: str
    tool_name: str
    arguments_fingerprint: str
    created_at: float
    expires_at: float
    used: bool = False
    revoked: bool = False
    # The approved arguments, kept so operators can audit what was
    # approved. Contains only what the caller asked to approve.
    arguments: Dict[str, Any] = field(default_factory=dict)


class ConfirmationGate:
    """Mint, verify, and consume single-use tool approvals.

    Thread-safe. All state is in-memory: a process restart invalidates
    every outstanding approval, which is the fail-closed behaviour.
    """

    def __init__(self, default_ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self._default_ttl = max(1.0, float(default_ttl_seconds))
        self._lock = threading.Lock()
        self._approvals: Dict[str, Approval] = {}

    def grant(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        ttl_seconds: Optional[float] = None,
    ) -> Approval:
        """Grant a single-use approval for one exact (tool, arguments) pair."""
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError("approval tool_name must be a non-empty string")
        fingerprint = _fingerprint(arguments)
        ttl = self._default_ttl if ttl_seconds is None else float(ttl_seconds)
        if ttl <= 0:
            raise ValueError("approval ttl_seconds must be positive")
        ttl = min(ttl, _MAX_TTL_SECONDS)
        now = time.time()
        approval = Approval(
            token=secrets.token_urlsafe(32),
            tool_name=tool_name,
            arguments_fingerprint=fingerprint,
            created_at=now,
            expires_at=now + ttl,
            arguments=dict(arguments),
        )
        with self._lock:
            self._approvals[approval.token] = approval
        return approval

    def _is_valid(
        self, approval: Approval, tool_name: str, fingerprint: str, now: float
    ) -> bool:
        return (
            not approval.used
            and not approval.revoked
            and approval.expires_at > now
            and approval.tool_name == tool_name
            and approval.arguments_fingerprint == fingerprint
        )

    def consume(self, token: str, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Consume *token* for one exact (tool, arguments) execution.

        Returns ``True`` only if the token exists, is unused, unrevoked,
        unexpired, and bound to exactly this tool and arguments. A
        successful consume marks the approval used, so replaying the same
        token always fails.
        """
        try:
            fingerprint = _fingerprint(arguments)
        except ValueError:
            return False
        with self._lock:
            approval = self._approvals.get(token)
            if approval is None:
                return False
            if not self._is_valid(approval, tool_name, fingerprint, time.time()):
                return False
            approval.used = True
            return True

    def consume_matching(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Consume any outstanding approval bound to (tool, arguments).

        Used by entry points where the user pre-approved an exact action
        (e.g. via the server approval endpoint) before the agent run
        decided to take it. Matching is by exact argument fingerprint,
        never by tool name alone.
        """
        try:
            fingerprint = _fingerprint(arguments)
        except ValueError:
            return False
        now = time.time()
        with self._lock:
            for approval in self._approvals.values():
                if self._is_valid(approval, tool_name, fingerprint, now):
                    approval.used = True
                    return True
        return False

    def revoke(self, token: str) -> bool:
        """Revoke *token* so it can never be consumed. Returns True if found."""
        with self._lock:
            approval = self._approvals.get(token)
            if approval is None:
                return False
            approval.revoked = True
            return True

    def purge_expired(self) -> int:
        """Drop expired approvals. Returns the number removed."""
        now = time.time()
        with self._lock:
            expired = [t for t, a in self._approvals.items() if a.expires_at <= now]
            for token in expired:
                del self._approvals[token]
        return len(expired)


__all__ = [
    "Approval",
    "ConfirmationGate",
    "canonical_arguments",
]
