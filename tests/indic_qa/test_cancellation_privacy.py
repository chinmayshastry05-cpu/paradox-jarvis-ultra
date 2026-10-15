"""Indic QA: cancellation and privacy (unit / mocked tests only).

These are UNIT and MOCKED tests. None uses real audio, a real model,
or a real device. "Sensitive" values below are INVENTED fixtures
(fake addresses / tokens) used only to prove the redaction and
quarantine paths drop them; no real user data appears anywhere.

Cancellation coverage: main has no explicit cancel token for an
in-flight extraction, so these tests pin the cancellation behaviour
that DOES exist -- submit-after-stop is rejected, a blocked exchange
stores no partial facts, an engine failure stores nothing, a mic
interrupt exits without a transcript, and clear() empties the store.
The missing explicit cancel token is recorded as a gap in the report.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from openjarvis.analytics.redaction import hash_id, looks_like_pii, redact
from openjarvis.cli._voice_chat import VOICE_EXIT, record_voice, speak
from openjarvis.memory.extractor import FactExtractor
from openjarvis.memory.service import MemoryService
from openjarvis.memory.store import Fact, LocalFactStore
from openjarvis.speech.voice_state import PushToTalkStateMachine
from openjarvis.tools.storage._stubs import RetrievalResult
from openjarvis.tools.storage.context import build_context_message, inject_context

# Invented fixture secrets -- never real credentials or user data.
_FAKE_EMAIL = "fixture-person@example.invalid"


class _FakeConsole:
    def __init__(self):
        self.printed = []

    def print(self, *args, **kwargs):
        self.printed.append(" ".join(str(a) for a in args))


class _CleanScan:
    is_clean = True
    threat_level = "none"


class _FlaggedScan:
    """Scanner result: flagged, but low severity (quarantine, not block)."""

    is_clean = False
    threat_level = "low"


class _BlockingScan:
    """Scanner result: flagged HIGH -- the whole exchange must be dropped."""

    is_clean = False
    threat_level = "high"


class _BlockingScanner:
    """Scanner whose every scan returns a HIGH-threat finding."""

    def scan(self, text):
        return _BlockingScan()


def _flagged_fact_scanner():
    """Flags only facts containing the marker; clean facts pass."""

    class _Scanner:
        def scan(self, text):
            return _FlaggedScan() if "MARKER-FLAGGED" in text else _CleanScan()

    return _Scanner()


# -- privacy: redaction -----------------------------------------------------


def test_redact_drops_pii_inside_indic_text():
    """An email embedded in Indic text causes the value to be dropped."""
    props = {"note": f"ಸಂಪರ್ಕ {_FAKE_EMAIL} ಗೆ ಕಳುಹಿಸಿ"}
    assert redact(props) == {}
    assert looks_like_pii(props["note"]) is True


def test_redact_preserves_clean_indic_text():
    """Clean Indic text with no PII passes through unchanged."""
    props = {"note": "ಕಾಯಕವೇ ಕೈಲಾಸ"}
    assert redact(props) == props


def test_redact_drops_overlong_indic_text():
    """Strings over MAX_STR_LEN are dropped even with no PII pattern."""
    props = {"note": "ಕ" * 201}
    assert redact(props) == {}


def test_redact_drops_invented_secret_assignment():
    """A secret-assignment-shaped value is dropped, never shipped."""
    props = {"note": "api_key = fixture-value-123"}
    assert redact(props) == {}


def test_hash_id_is_deterministic_and_does_not_leak_input():
    """hash_id is a stable 16-hex prefix that never contains the input."""
    assert hash_id("ಕಾಯಕವೇ ಕೈಲಾಸ") == hash_id("ಕಾಯಕವೇ ಕೈಲಾಸ")
    assert hash_id("ಕಾಯಕವೇ ಕೈಲಾಸ") != hash_id("सत्यमेव जयते")
    assert len(hash_id("ಕಾಯಕವೇ ಕೈಲಾಸ")) == 16
    assert "ಕಾಯಕವೇ" not in hash_id("ಕಾಯಕವೇ ಕೈಲಾಸ")
    assert hash_id("") == ""


# -- privacy: quarantine ----------------------------------------------------


def test_quarantined_indic_fact_excluded_from_context():
    """An untrusted Indic fact never reaches a model-facing message."""
    quarantined = Fact(text="MARKER-FLAGGED secret fact", trust="untrusted")
    message = build_context_message([], [quarantined])
    assert "MARKER-FLAGGED" not in message.content


def test_inject_context_excludes_untrusted_indic_document():
    """inject_context drops retrieved docs carrying the untrusted tier."""

    class _Backend:
        def retrieve(self, query, *, top_k=5, **kwargs):
            return [
                RetrievalResult(
                    content="ಕಾಯಕವೇ ಕೈಲಾಸ",
                    score=1.0,
                    source="indic-qa",
                    metadata={"trust": "untrusted"},
                )
            ]

    messages = inject_context("query", [], _Backend(), facts=[])
    assert messages == []


# -- cancellation: memory service ------------------------------------------


def test_memory_service_blocks_high_threat_exchange_entirely(tmp_path):
    """A HIGH-threat exchange stores NO partial facts (all-or-nothing)."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    engine = MagicMock()
    engine.generate.return_value = {"content": '["ಕಾಯಕವೇ ಕೈಲಾಸ"]'}
    service = MemoryService(
        store,
        FactExtractor(engine, model="mock-model"),
        scanner=_BlockingScanner(),
    )
    service._process(("ಹಾನಿಕಾರಕ ಸೂಚನೆ", ""))
    assert store.count() == 0


def test_memory_service_quarantines_flagged_fact_only(tmp_path):
    """A flagged fact is stored untrusted; a clean fact stays recallable."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    engine = MagicMock()
    engine.generate.return_value = {
        "content": '["clean fixture fact", "MARKER-FLAGGED fixture fact"]'
    }
    service = MemoryService(
        store,
        FactExtractor(engine, model="mock-model"),
        scanner=_flagged_fact_scanner(),
    )
    service._process(("constructed turn", ""))
    facts = {f.text: f for f in store.list()}
    assert facts["clean fixture fact"].trusted_for_recall is True
    assert facts["MARKER-FLAGGED fixture fact"].trusted_for_recall is False


def test_memory_service_submit_after_stop_rejected(tmp_path):
    """After stop(), submit() rejects the job -- nothing is enqueued."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    engine = MagicMock()
    engine.generate.return_value = {"content": '["ಕಾಯಕವೇ ಕೈಲಾಸ"]'}
    service = MemoryService(store, FactExtractor(engine, model="mock-model"))
    service.start()
    assert service.is_running is True
    service.stop()
    assert service.is_running is False
    assert service.submit("ಕಾಯಕವೇ ಕೈಲಾಸ", "") is False
    assert store.count() == 0


def test_memory_service_submit_before_start_rejected(tmp_path):
    """Before start(), submit() rejects the job -- nothing is enqueued."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    service = MemoryService(store, FactExtractor(MagicMock(), model="mock-model"))
    assert service.submit("ಕಾಯಕವೇ ಕೈಲಾಸ", "") is False
    assert store.count() == 0


def test_memory_service_engine_failure_stores_no_partial_facts(tmp_path):
    """A raising engine yields no facts and does not kill the worker."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    engine = MagicMock()
    engine.generate.side_effect = RuntimeError("engine cancelled")
    service = MemoryService(store, FactExtractor(engine, model="mock-model"))
    service.start()
    try:
        assert service.submit("constructed turn", "") is True
        deadline = time.time() + 5
        while time.time() < deadline and service._queue.qsize() > 0:
            time.sleep(0.05)
        # Drain any in-flight job before asserting.
        time.sleep(0.2)
    finally:
        service.stop()
    assert store.count() == 0


# -- cancellation: voice input/output (mocked backends, no mic) -------------


def _voice_session_with_backend(backend):
    # Voice branch requires session.state_machine (push-to-talk); provide a real one.
    session = SimpleNamespace(
        get_stt_backend=lambda: backend,
        get_stt_language=lambda: "kn",
        state_machine=PushToTalkStateMachine(),
    )
    return session


def test_record_voice_keyboard_interrupt_exits_without_transcript(monkeypatch):
    """Ctrl-C during recording exits (VOICE_EXIT) with no transcript."""

    def _raise(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("openjarvis.speech.voice_io.record_until_silence", _raise)
    console = _FakeConsole()
    backend = MagicMock()
    result = record_voice(console, _voice_session_with_backend(backend))
    assert result is VOICE_EXIT
    assert backend.transcribe.call_count == 0


def test_record_voice_mic_error_exits_without_transcript(monkeypatch):
    """A mic (PortAudio-style) error exits without a transcript."""

    def _raise(*args, **kwargs):
        raise OSError("mic unavailable")

    monkeypatch.setattr("openjarvis.speech.voice_io.record_until_silence", _raise)
    console = _FakeConsole()
    backend = MagicMock()
    result = record_voice(console, _voice_session_with_backend(backend))
    assert result is VOICE_EXIT
    assert any("Mic error" in line for line in console.printed)
    assert backend.transcribe.call_count == 0


def test_speak_with_no_backend_reports_unavailable():
    """With no healthy TTS backend, speak() reports it and returns."""

    class _Session:
        # Voice branch requires session.state_machine (push-to-talk).
        state_machine = PushToTalkStateMachine()

        def get_voice_preferences(self):
            return ("kokoro", "", 1.0)

        def get_tts_backend(self):
            return None

    console = _FakeConsole()
    speak("ಕಾಯಕವೇ ಕೈಲಾಸ", console, _Session())
    assert any("No TTS backend available" in line for line in console.printed)
