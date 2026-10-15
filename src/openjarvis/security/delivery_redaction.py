"""Fail-closed redaction for anything delivered to a client.

Every streaming / SSE / WebSocket / CLI delivery path must pass outgoing
text and structured payloads through here *before* emission. The previous
behaviour in ``server/stream_bridge.py`` returned text unchanged when the
scanner could not be imported — fail-open — so a scanner outage leaked
whatever the payload contained.

Fail-closed ladder in :func:`redact_text`:

1. Rust ``SecretScanner`` (same patterns as the engine guardrails).
2. Pure-Python regex fallback using patterns that mirror
   ``SecretScanner.PATTERNS`` / the Rust ``SECRET_PATTERNS`` (kept in this
   module so the fallback still works when ``scanner.py`` itself fails to
   import). Tests assert the fallback redacts the same sample secrets as
   the Rust scanner, so drift between the two lists is caught.
3. If both fail, the whole payload is replaced by a blocked placeholder —
   never returned raw.

:func:`redact_value` applies the same rule recursively to structured
payloads (tool-call arguments, tool results, named SSE event data).
Values that cannot be scanned (arbitrary objects, undecodable bytes,
cycles, over-deep nesting) are replaced by a placeholder instead of being
stringified — ``repr``/``str`` of an arbitrary object can itself contain
a secret.

Split secrets: :class:`StreamingRedactor` buffers token streams and
holds back a tail, so a secret split across tokens of *one* logical
payload is recognised before any of its bytes are emitted. Callers that
already hold a whole payload (final agent content, one discrete SSE
event, one tool result) must use :func:`redact_text` /
:func:`redact_value` on the whole payload, not the streaming redactor.

Boundary (cannot be fixed at this layer, documented so callers do not
assume otherwise):

* Segments already emitted cannot be retracted. The redactor holds a
  tail (default 1024 chars) plus any trailing partial-pattern prefix, so
  secrets up to that length split across tokens are caught. A secret
  longer than the holdback whose prefix alone matches no pattern could
  leak its leading bytes before the pattern becomes recognisable — an
  inherent limit of streaming redaction, not of whole-payload redaction.
* A secret deliberately split across two *discrete* named events, with
  neither half matching a pattern on its own, is not reconstructed.
  Callers must not split one logical payload across discrete events.
* Error paths must never embed exception text: use
  :func:`safe_error_message`. The full exception stays in server logs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import Any

__all__ = [
    "BLOCKED_PLACEHOLDER",
    "StreamingRedactor",
    "redact_text",
    "redact_value",
    "safe_error_message",
]

BLOCKED_PLACEHOLDER = "[REDACTED: delivery blocked — secret scanner unavailable]"
_UNSCANNABLE_PLACEHOLDER = "[REDACTED: unscannable value]"
_MAX_DEPTH = 20

# Pure-Python fallback patterns. Must mirror SecretScanner.PATTERNS in
# openjarvis/security/scanner.py and SECRET_PATTERNS in
# rust/crates/openjarvis-security/src/scanner.rs (same names, same regexes).
_FALLBACK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("openai_key", r"sk-[A-Za-z0-9_-]{20,}"),
    ("anthropic_key", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("aws_access_key", r"AKIA[0-9A-Z]{16}"),
    ("github_token", r"(?:ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}"),
    (
        "password_assignment",
        r"""(?:password|passwd|pwd)\s*[=:]\s*['"]([^'"]{4,})['"]""",
    ),
    ("db_connection_string", r"(?:postgres|mysql|mongodb|redis)://[^\s]{10,}"),
    ("private_key", r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    ("slack_token", r"xox[bpors]-[A-Za-z0-9\-]{10,}"),
    ("stripe_key", r"(?:sk|pk)_(?:test|live)_[A-Za-z0-9]{20,}"),
    (
        "generic_api_key",
        r"""(?:api_key|secret_key|auth_token)\s*[=:]\s*['"]([^'"]{8,})['"]""",
    ),
)
_FALLBACK_COMPILED: tuple[tuple[str, "re.Pattern[str]"], ...] = tuple(
    (name, re.compile(pattern)) for name, pattern in _FALLBACK_PATTERNS
)

# Suffixes that may be the *start* of a secret whose remainder has not
# arrived yet. Checked anchored at the end of an emitted prefix; a match
# means that suffix is held back instead of emitted.
_PARTIAL_PATTERNS: tuple[str, ...] = (
    r"sk-[A-Za-z0-9_-]{0,19}$",
    r"sk-ant-[A-Za-z0-9_-]{0,19}$",
    r"AKIA[0-9A-Z]{0,15}$",
    r"(?:ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{0,35}$",
    r"xox[bpors]-[A-Za-z0-9\-]{0,9}$",
    r"(?:sk|pk)_(?:test|live)?_?[A-Za-z0-9]{0,19}$",
    r"(?:password|passwd|pwd)\s*[=:]\s*['\"]?[^'\"]{0,}$",
    r"(?:api_key|secret_key|auth_token)\s*[=:]\s*['\"]?[^'\"]{0,}$",
    r"(?:postgres|mysql|mongodb|redis)://[^\s]{0,}$",
    r"-----BEGIN (?:RSA )?PRIVATE KEY-----$",
    r"-----BEGIN( ?$| (?:RSA)? ?$| (?:RSA )?PRIVATE( ?$| KEY( ?$|-{0,4}$)))",
)
_PARTIAL_COMPILED: tuple["re.Pattern[str]", ...] = tuple(
    re.compile(p) for p in _PARTIAL_PATTERNS
)


def _redact_with_fallback(text: str) -> str:
    result = text
    for name, pattern in _FALLBACK_COMPILED:
        result = pattern.sub(f"[REDACTED:{name}]", result)
    return result


def redact_text(text: str) -> str:
    """Redact secrets from *text*, fail-closed.

    Never returns raw text on scanner failure: falls back to the
    pure-Python patterns, and if those fail too returns the blocked
    placeholder.
    """
    if not isinstance(text, str):
        return _UNSCANNABLE_PLACEHOLDER
    try:
        from openjarvis.security.scanner import SecretScanner

        return SecretScanner().redact(text)
    except Exception:
        pass
    try:
        return _redact_with_fallback(text)
    except Exception:
        return BLOCKED_PLACEHOLDER


def redact_value(
    value: Any, _depth: int = 0, _seen: frozenset[int] | None = None
) -> Any:
    """Recursively redact secrets in a structured payload, fail-closed."""
    try:
        return _redact_value_inner(value, _depth, _seen or frozenset())
    except Exception:
        return BLOCKED_PLACEHOLDER


def _redact_value_inner(value: Any, depth: int, seen: frozenset[int]) -> Any:
    if depth > _MAX_DEPTH:
        return _UNSCANNABLE_PLACEHOLDER
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return redact_text(bytes(value).decode("utf-8"))
        except Exception:
            return _UNSCANNABLE_PLACEHOLDER
    if isinstance(value, dict):
        oid = id(value)
        if oid in seen:
            return _UNSCANNABLE_PLACEHOLDER
        seen = seen | {oid}
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str):
                new_key = redact_text(key)
            else:
                new_key = _UNSCANNABLE_PLACEHOLDER
            out[new_key] = _redact_value_inner(item, depth + 1, seen)
        return out
    if isinstance(value, (list, tuple)):
        oid = id(value)
        if oid in seen:
            return _UNSCANNABLE_PLACEHOLDER
        seen = seen | {oid}
        return [_redact_value_inner(item, depth + 1, seen) for item in value]
    if isinstance(value, (set, frozenset)):
        oid = id(value)
        if oid in seen:
            return _UNSCANNABLE_PLACEHOLDER
        seen = seen | {oid}
        return [_redact_value_inner(item, depth + 1, seen) for item in value]
    # Pydantic models / dataclasses: redact their data, not their repr.
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _redact_value_inner(model_dump(), depth + 1, seen)
        except Exception:
            return _UNSCANNABLE_PLACEHOLDER
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return _redact_value_inner(asdict(value), depth + 1, seen)
        except Exception:
            return _UNSCANNABLE_PLACEHOLDER
    # Anything else could leak via __str__/__repr__ — do not stringify it.
    return _UNSCANNABLE_PLACEHOLDER


def safe_error_message(kind: str = "stream") -> str:
    """Fixed client-facing error text carrying no exception content."""
    messages = {
        "stream": "An error occurred while streaming. See server logs for details.",
        "chat": "Sorry, an error occurred. See server logs for details.",
        "context_length": (
            "The input is too long for the model's context window. "
            "Please try a shorter message."
        ),
        "model": "The model returned an error. See server logs for details.",
        "research": "Research failed. See server logs for details.",
        "tool": "Tool execution failed. See server logs for details.",
    }
    return messages.get(kind, messages["stream"])


def _emit_cut(buffer: str, emit_end: int) -> int:
    """Shrink *emit_end* so no emitted prefix starts an unfinished secret.

    A secret may start inside the emit prefix and continue into the held
    tail (crossing match), or start inside the emit prefix and run past
    the end of the buffer so far (partial match). In either case the
    emit prefix is cut at the secret's start and the remainder stays
    held. Redacting each small emit slice in isolation would leak such
    a secret piece by piece, so the boundary check runs on the whole
    buffer, not on the slice alone.
    """
    for _, pattern in _FALLBACK_COMPILED:
        for match in pattern.finditer(buffer):
            if match.start() < emit_end < match.end():
                emit_end = match.start()
    for pattern in _PARTIAL_COMPILED:
        match = pattern.search(buffer)
        if match and match.start() < emit_end and match.end() == len(buffer):
            emit_end = min(emit_end, match.start())
    return emit_end


class StreamingRedactor:
    """Buffer token streams so split secrets are redacted before emission.

    :meth:`feed` returns only the prefix that is safe to emit now: the
    trailing ``holdback`` chars plus any trailing partial-pattern prefix
    are held. :meth:`flush` redacts and returns the remainder. See the
    module docstring for the boundary (secrets longer than the holdback
    whose prefix matches no pattern).
    """

    def __init__(self, holdback: int = 1024) -> None:
        self._holdback = max(0, int(holdback))
        self._buffer = ""

    def feed(self, text: str) -> str:
        if not isinstance(text, str) or not text:
            return ""
        self._buffer += text
        if len(self._buffer) <= self._holdback:
            return ""
        emit_end = _emit_cut(self._buffer, len(self._buffer) - self._holdback)
        if emit_end <= 0:
            return ""
        emit, self._buffer = self._buffer[:emit_end], self._buffer[emit_end:]
        return redact_text(emit)

    def flush(self) -> str:
        remainder, self._buffer = self._buffer, ""
        if not remainder:
            return ""
        return redact_text(remainder)
