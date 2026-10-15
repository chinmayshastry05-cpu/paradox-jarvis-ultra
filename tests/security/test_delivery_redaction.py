"""Fail-closed delivery redaction: scanner failure must never leak raw text."""

from __future__ import annotations

import pytest

import openjarvis.security.delivery_redaction as dr
from openjarvis.security.delivery_redaction import (
    BLOCKED_PLACEHOLDER,
    StreamingRedactor,
    redact_text,
    redact_value,
    safe_error_message,
)

# Synthetic samples only — never real credentials.
OPENAI_SAMPLE = "sk-abcdefghij1234567890ABCD"
AWS_SAMPLE = "AKIAIOSFODNN7EXAMPLE"
GITHUB_SAMPLE = "ghp_" + "a" * 36


def test_rust_scanner_redacts_samples():
    pytest.importorskip("openjarvis_rust")
    assert "sk-" not in redact_text(f"key {OPENAI_SAMPLE} end")
    assert "AKIA" not in redact_text(f"key {AWS_SAMPLE} end")


def test_fallback_redacts_when_rust_scanner_fails(monkeypatch):
    """Scanner import/runtime failure -> pure-Python fallback, not raw."""
    import openjarvis.security.scanner as scanner_mod

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("scanner unavailable")

    monkeypatch.setattr(scanner_mod, "SecretScanner", _Boom)
    assert OPENAI_SAMPLE not in redact_text(f"key {OPENAI_SAMPLE}")
    assert "[REDACTED:openai_key]" in redact_text(f"key {OPENAI_SAMPLE}")
    assert AWS_SAMPLE not in redact_text(f"key {AWS_SAMPLE}")
    assert GITHUB_SAMPLE not in redact_text(f"token {GITHUB_SAMPLE}")


def test_total_failure_blocks_instead_of_leaking(monkeypatch):
    """Both Rust and fallback failing -> placeholder, never raw text."""
    import openjarvis.security.scanner as scanner_mod

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("scanner unavailable")

    monkeypatch.setattr(scanner_mod, "SecretScanner", _Boom)
    monkeypatch.setattr(
        dr,
        "_redact_with_fallback",
        lambda text: (_ for _ in ()).throw(RuntimeError("fallback down")),
    )
    assert redact_text(f"key {OPENAI_SAMPLE}") == BLOCKED_PLACEHOLDER


def test_redact_value_structured():
    payload = {
        "tool": "search",
        "arguments": {"api_key": OPENAI_SAMPLE, "nested": [AWS_SAMPLE]},
        "count": 3,
        "ok": True,
        "nothing": None,
    }
    out = redact_value(payload)
    assert OPENAI_SAMPLE not in str(out)
    assert AWS_SAMPLE not in str(out)
    assert out["count"] == 3
    assert out["ok"] is True
    assert out["nothing"] is None


def test_redact_value_unscannable_and_cycles():
    class _Secretive:
        def __repr__(self):
            return f"leak {OPENAI_SAMPLE}"

    cyclic: dict = {}
    cyclic["self"] = cyclic
    cyclic["obj"] = _Secretive()
    cyclic["raw"] = b"bytes " + OPENAI_SAMPLE.encode()
    out = redact_value(cyclic)
    assert OPENAI_SAMPLE not in str(out)
    assert out["self"] == "[REDACTED: unscannable value]"
    assert out["obj"] == "[REDACTED: unscannable value]"
    # Decodable bytes are scanned, not passed through raw.
    assert "[REDACTED:openai_key]" in out["raw"]


def test_redact_value_deep_nesting_blocked():
    deep: object = "leaf"
    for _ in range(30):
        deep = [deep]
    assert "[REDACTED: unscannable value]" in str(redact_value(deep))


def test_safe_error_message_carries_no_exception_text():
    for kind in ("stream", "chat", "context_length", "model", "research", "tool"):
        msg = safe_error_message(kind)
        assert OPENAI_SAMPLE not in msg
        assert "sk-" not in msg
    assert safe_error_message("unknown-kind") == safe_error_message("stream")


def test_streaming_redactor_split_secret_across_tokens():
    redactor = StreamingRedactor(holdback=8)
    emitted = []
    secret = f"prefix {OPENAI_SAMPLE} suffix"
    for ch in secret:
        emitted.append(redactor.feed(ch))
    emitted.append(redactor.flush())
    joined = "".join(emitted)
    assert OPENAI_SAMPLE not in joined
    assert "[REDACTED:openai_key]" in joined
    assert "prefix" in joined and "suffix" in joined


def test_streaming_redactor_holds_partial_prefix():
    redactor = StreamingRedactor(holdback=4)
    first = redactor.feed("hello sk-")
    assert "sk-" not in first
    # Feed the rest; the held prefix must never have been emitted raw.
    out = first + redactor.feed("abcdefghij1234567890ABCD done") + redactor.flush()
    assert OPENAI_SAMPLE not in out
    assert "[REDACTED:openai_key]" in out


def test_streaming_redactor_clean_text_round_trips():
    redactor = StreamingRedactor(holdback=4)
    parts = [redactor.feed("hello "), redactor.feed("world"), redactor.flush()]
    assert "".join(parts) == "hello world"


def test_research_sse_redacts_structured_event():
    pytest.importorskip("fastapi")
    from openjarvis.server.research_router import _sse

    sample = "sk-abcdefghij1234567890ABCD"
    frame = _sse(
        {"type": "trace", "text": f"found {sample}", "sources": [{"url": sample}]}
    )
    assert sample not in frame
    assert "[REDACTED:openai_key]" in frame


def test_research_sse_malformed_event_never_emits_raw():
    pytest.importorskip("fastapi")
    from openjarvis.server.research_router import _sse

    cyclic: dict = {}
    cyclic["self"] = cyclic
    frame = _sse(cyclic)  # type: ignore[arg-type]
    assert "self" in frame  # placeholder frame still serialises


def test_streaming_redactor_clean_tokens_stream_immediately():
    """Clean tokens are not batched: only a suspicious tail is held."""
    redactor = StreamingRedactor()
    assert redactor.feed("Hello") == "Hello"
    assert redactor.feed(" ") == " "
    assert redactor.feed("world") == "world"
    assert redactor.flush() == ""


def test_streaming_redactor_flush_replaces_strong_partial_fragment():
    redactor = StreamingRedactor()
    assert redactor.feed("hello sk-abc") == "hello "
    assert redactor.flush() == "[REDACTED:partial-secret]"


def test_streaming_redactor_split_secret_single_char_pieces():
    """A secret split inside its literal prefix is still caught."""
    redactor = StreamingRedactor()
    emitted = [redactor.feed("s"), redactor.feed("k-")]
    emitted.append(redactor.feed("abcdefghij1234567890ABCD end"))
    emitted.append(redactor.flush())
    joined = "".join(emitted)
    assert "sk-abcdefghij1234567890ABCD" not in joined
    assert "[REDACTED:openai_key]" in joined


# --- Regression tests: assignment-secret leaks across exact-name splits ---
#
# With the scanner absent (fallback active), a two-chunk split of
# ``password = "VALUE"`` at the exact end of the literal name leaked
# the whole assignment: the literal-prefix loop excluded the complete
# literal (``range(1, len)``), and the partial pattern required the
# separator. The same held for ``api_key``. These tests cover EVERY
# two-chunk split position and 1-character feeds for every pattern,
# with the scanner forced off, and assert the secret VALUE never
# appears raw.

_ASSIGNMENT_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("password", "SYNTH-PW-1234-ABCD"),
    ("passwd", "SYNTH-PW-2345-BCDE"),
    ("pwd", "SYNTH-PW-3456-CDEF"),
    ("api_key", "SYNTH-API-4567-DEFG"),
    ("secret_key", "SYNTH-SK-5678-EFGH"),
    ("auth_token", "SYNTH-AT-6789-FGHI"),
)
_TOKEN_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("sk-", "A" * 24),
    ("sk-ant-", "B" * 24),
    ("AKIA", "C" * 16),
    ("ghp_", "d" * 36),
    ("postgres://", "user:pass@host/dbname"),
    ("-----BEGIN PRIVATE KEY-----", ""),
    ("xoxb-", "e" * 12),
    ("sk_live_", "f" * 24),
)


def _force_fallback(monkeypatch):
    """Make redact_text use the pure-Python fallback (scanner absent)."""
    import openjarvis.security.scanner as scanner_mod

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("scanner absent")

    monkeypatch.setattr(scanner_mod, "SecretScanner", _Boom)


def _assignment_text(name: str, value: str, sep: str = "=") -> str:
    return f"prefix {name} {sep} \"{value}\" suffix"


def test_streaming_redactor_assignment_exact_name_split(monkeypatch):
    """Reviewer repro: split exactly after the literal name leaks."""
    _force_fallback(monkeypatch)
    for name, value in _ASSIGNMENT_EXAMPLES:
        for sep in ("=", ":"):
            text = _assignment_text(name, value, sep)
            split = text.index(name) + len(name)
            r = StreamingRedactor()
            out = r.feed(text[:split]) + r.feed(text[split:]) + r.flush()
            assert value not in out, f"{name!r} {sep!r} split leaked"


def test_streaming_redactor_assignment_whitespace_split(monkeypatch):
    """Literal + trailing whitespace, then separator + value: held."""
    _force_fallback(monkeypatch)
    for name, value in _ASSIGNMENT_EXAMPLES:
        text = f"prefix {name}  = \"{value}\" suffix"
        split = text.index(name) + len(name) + 2  # after the spaces
        r = StreamingRedactor()
        out = r.feed(text[:split]) + r.feed(text[split:]) + r.flush()
        assert value not in out, f"{name!r} whitespace split leaked"


def test_streaming_redactor_every_split_position(monkeypatch):
    """Exhaustive: every two-chunk split of every pattern example."""
    _force_fallback(monkeypatch)
    cases: list[tuple[str, str]] = []
    for name, value in _ASSIGNMENT_EXAMPLES:
        cases.append((_assignment_text(name, value), value))
    for literal, rest in _TOKEN_EXAMPLES:
        token = literal + rest
        cases.append((f"prefix {token} suffix", token))
    for text, secret in cases:
        for i in range(1, len(text)):
            r = StreamingRedactor()
            out = r.feed(text[:i]) + r.feed(text[i:]) + r.flush()
            assert secret not in out, (
                f"split at {i} of {text!r} leaked {secret!r}"
            )


def test_streaming_redactor_every_split_one_char_feeds(monkeypatch):
    """Exhaustive 1-character feeds for every pattern example."""
    _force_fallback(monkeypatch)
    cases: list[tuple[str, str]] = []
    for name, value in _ASSIGNMENT_EXAMPLES:
        cases.append((_assignment_text(name, value), value))
    for literal, rest in _TOKEN_EXAMPLES:
        token = literal + rest
        cases.append((f"prefix {token} suffix", token))
    for text, secret in cases:
        r = StreamingRedactor()
        parts = [r.feed(ch) for ch in text]
        parts.append(r.flush())
        assert secret not in "".join(parts), f"1-char feeds leaked {secret!r}"


def test_streaming_redactor_bare_literal_emitted_raw_at_flush(monkeypatch):
    """A bare literal with no value is not a secret: no corruption."""
    _force_fallback(monkeypatch)
    r = StreamingRedactor()
    out = r.feed("my password ") + r.flush()
    assert out == "my password "
    r = StreamingRedactor()
    out = r.feed("note api_key") + r.flush()
    assert out == "note api_key"


# --- Regression tests: overlong streaming secret continuation ---
#
# After an oversized suspicious suffix was dropped, the redactor reset
# its state, so continuation bytes in the next feed matched no pattern
# and emitted raw. The redactor must stay in suppression until a safe
# separator (closing quote of an unclosed quoted value, else the first
# whitespace / quote).


def test_streaming_redactor_overlong_continuation_suppressed():
    r = StreamingRedactor()
    seg1 = r.feed("sk-" + "A" * 66000)
    assert "[REDACTED:overlong-partial-secret]" in seg1
    seg2 = r.feed("A" * 100)
    assert seg2 == "", f"continuation leaked: {seg2[:50]!r}"
    assert r.flush() == ""


def test_streaming_redactor_overlong_resumes_after_separator():
    r = StreamingRedactor()
    r.feed("sk-" + "A" * 66000)
    out = r.feed("A" * 50 + " clean tail") + r.flush()
    assert "clean tail" in out
    assert "A" not in out


def test_streaming_redactor_overlong_quoted_value_waits_for_quote():
    """Whitespace inside a quoted value must NOT end suppression."""
    r = StreamingRedactor()
    r.feed('password="' + "B" * 66000)
    # Continuation with an inner space: still suppressed (no closing quote).
    assert r.feed("B" * 50 + " inner space") == ""
    # Closing quote ends suppression; text after it streams.
    out = r.feed('B" after') + r.flush()
    assert "after" in out
    assert "B" not in out
