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

* Segments already emitted cannot be retracted. The redactor holds
  back only a trailing suffix that could grow into a secret (a
  complete match at the buffer end, a partial-pattern match, or a
  literal pattern prefix), so a secret split across tokens of one
  payload is caught however long it is, while clean tokens still
  stream immediately. The residual limit: a secret whose pattern is
  not in the scanner's list cannot be recognised at all — same as
  whole-payload redaction.
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


# Literal prefixes of the secret patterns above. Every secret starts
# with one of these, so any fragment that is a prefix of a secret is
# either a prefix of one of these literals, a partial-pattern match, or
# already a complete match. Used to hold back a suffix that could grow
# into a secret on the next token.
_LITERAL_PREFIXES: tuple[str, ...] = (
    "sk-",
    "sk-ant-",
    "AKIA",
    "ghp_",
    "gho_",
    "ghs_",
    "ghr_",
    "github_pat_",
    "password",
    "passwd",
    "pwd",
    "postgres://",
    "mysql://",
    "mongodb://",
    "redis://",
    "-----BEGIN ",
    "-----BEGIN RSA PRIVATE KEY-----",
    "xoxb-",
    "xoxp-",
    "xoxo-",
    "xoxr-",
    "xoxs-",
    "sk_live_",
    "sk_test_",
    "pk_live_",
    "pk_test_",
    "api_key",
    "secret_key",
    "auth_token",
)
_MAX_BUFFERED = 65536


def _suspicious_start(buffer: str, *, final: bool = False) -> int:
    """Earliest index of a suffix of *buffer* that may become a secret.

    Returns ``len(buffer)`` when no suffix is suspicious. A suffix is
    suspicious when it is: a complete-pattern match ending exactly at
    the end (extendable — only while streaming, ``final=False``), a
    partial-pattern match ending at the end, or — while streaming — a
    proper prefix of a literal pattern prefix. At ``final=True`` a
    literal-prefix-only suffix is emitted raw: it is not a usable
    secret (a single char such as ``"s"``), while a strong partial
    match is replaced by a marker by :meth:`StreamingRedactor.flush`.
    """
    end = len(buffer)
    cut = end
    if not final:
        for _, pattern in _FALLBACK_COMPILED:
            for match in pattern.finditer(buffer):
                if match.end() == end and match.start() < cut:
                    cut = match.start()
    for pattern in _PARTIAL_COMPILED:
        match = pattern.search(buffer)
        if match and match.end() == end and match.start() < cut:
            cut = match.start()
    if not final:
        for literal in _LITERAL_PREFIXES:
            for k in range(1, len(literal)):
                if buffer.endswith(literal[:k]) and end - k < cut:
                    cut = end - k
    return cut


class StreamingRedactor:
    """Buffer token streams so split secrets are redacted before emission.

    :meth:`feed` emits the incoming text immediately *except* for a
    trailing suffix that could grow into a secret on the next token
    (see :func:`_suspicious_start`). Clean tokens therefore still
    stream token-by-token; only a suspicious tail is held. A secret
    split across tokens is recognised once its final token arrives,
    before any of its bytes were emitted. :meth:`flush` redacts the
    remainder, replacing a trailing strong partial-secret fragment
    with a marker. See the module docstring for the boundary.
    """

    def __init__(self, holdback: int = 1024) -> None:
        # Retained for call-site compatibility; holding is suffix-driven,
        # not length-driven. The value is unused beyond the cap below.
        self._holdback = max(0, int(holdback))
        self._buffer = ""

    def feed(self, text: str) -> str:
        if not isinstance(text, str) or not text:
            return ""
        self._buffer += text
        if len(self._buffer) > _MAX_BUFFERED:
            # Bounded fail-closed: never emit an unbounded suspicious
            # suffix; drop it behind a marker instead of leaking it.
            cut = _suspicious_start(self._buffer)
            buffered, self._buffer = self._buffer, ""
            emit = redact_text(buffered[:cut])
            if cut < len(buffered):
                emit += "[REDACTED:overlong-partial-secret]"
            return emit
        cut = _suspicious_start(self._buffer)
        if cut <= 0:
            return ""
        emit, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return redact_text(emit)

    def flush(self) -> str:
        remainder, self._buffer = self._buffer, ""
        if not remainder:
            return ""
        cut = _suspicious_start(remainder, final=True)
        out = redact_text(remainder[:cut])
        if cut < len(remainder):
            out += "[REDACTED:partial-secret]"
        return out
