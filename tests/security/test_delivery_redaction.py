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
