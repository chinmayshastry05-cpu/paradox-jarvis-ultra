"""Indic QA: code-switch (mixed-script) text paths (unit / mocked tests).

These are UNIT and MOCKED tests. None uses real audio, a real model,
or a real device: the "engine" is a stub whose return value is supplied
by the test.

Source rule: every mixed-script string below is a CONSTRUCTED fixture
(an Indic-script fragment plus an English word). Each test asserts
byte-identical round-trip preservation and the presence of both
scripts (checked via the Unicode block ranges for Kannada
U+0C80-U+0CFF and Devanagari U+0900-U+097F). No translation or
grammatical correctness is asserted for any fixture string.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from openjarvis.cli._voice_chat import (
    VOICE_EXIT,
    _terminal_safe_text,
    read_voice_input,
)
from openjarvis.memory.extractor import FactExtractor
from openjarvis.memory.store import Fact, LocalFactStore
from openjarvis.tools.storage.chunking import chunk_text
from openjarvis.tools.storage.context import build_context_message

KANNADA = (0x0C80, 0x0CFF)
DEVANAGARI = (0x0900, 0x097F)
LATIN = (0x0041, 0x007A)

CODE_SWITCH_CASES = [
    ("kannada+english", "ನಾಳೆ meeting ಇದೆ"),
    ("hindi+english", "आज meeting है"),
    ("sanskrit+english", "सत्यमेव जयते meeting"),
    ("english+kannada", "meeting ನಾಳೆ ಇದೆ"),
]


def _has_script(text: str, block: tuple[int, int]) -> bool:
    lo, hi = block
    return any(lo <= ord(ch) <= hi for ch in text)


@pytest.mark.parametrize("label,text", CODE_SWITCH_CASES)
def test_fact_store_round_trips_code_switched_text(tmp_path, label, text):
    """LocalFactStore preserves mixed-script input verbatim."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    assert store.add(text, source="indic-qa") is True
    assert [f.text for f in store.list()] == [text]


@pytest.mark.parametrize("label,text", CODE_SWITCH_CASES)
def test_code_switched_text_contains_both_scripts(label, text):
    """Fixtures really are mixed-script (guard against a bad fixture)."""
    assert _has_script(text, LATIN)
    assert _has_script(text, KANNADA) or _has_script(text, DEVANAGARI)


@pytest.mark.parametrize("label,text", CODE_SWITCH_CASES)
def test_chunk_text_preserves_code_switched_text(label, text):
    """chunk_text returns mixed-script input unchanged in one chunk."""
    chunks = chunk_text(text, source="indic-qa")
    assert len(chunks) == 1
    assert chunks[0].content == text


def test_extractor_parses_code_switched_fact_from_mocked_engine():
    """FactExtractor returns a mocked-engine mixed-script fact verbatim."""
    engine = MagicMock()
    engine.generate.return_value = {"content": '["ನಾಳೆ meeting ಇದೆ"]'}
    extractor = FactExtractor(engine, model="mock-model")
    assert extractor.extract("constructed turn", "") == ["ನಾಳೆ meeting ಇದೆ"]


def test_context_message_preserves_code_switched_fact():
    """build_context_message carries a mixed-script fact into the prompt."""
    message = build_context_message([], [Fact(text="आज meeting है")])
    assert "आज meeting है" in message.content


def test_read_voice_input_returns_typed_code_switched_text(monkeypatch):
    """Typed mixed-script input passes through read_voice_input verbatim."""
    monkeypatch.setattr("builtins.input", lambda prompt="": "ನಾಳೆ meeting ಇದೆ")
    assert read_voice_input(console=None, session=None) == "ನಾಳೆ meeting ಇದೆ"


def test_read_voice_input_eof_exits_cleanly(monkeypatch):
    """EOF (Ctrl-D) on typed input maps to the VOICE_EXIT sentinel."""

    def _eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    assert read_voice_input(console=None, session=None) is VOICE_EXIT


def test_read_voice_input_keyboard_interrupt_exits_cleanly(monkeypatch):
    """Ctrl-C on typed input maps to the VOICE_EXIT sentinel."""

    def _interrupt(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _interrupt)
    assert read_voice_input(console=None, session=None) is VOICE_EXIT


def test_terminal_safe_text_strips_controls_and_escapes_markup():
    """Display sanitiser drops terminal controls and escapes Rich markup."""
    cleaned = _terminal_safe_text("ನಾಳೆ meeting \x00\x1b[31m [bold]hi")
    assert "\x00" not in cleaned
    assert "\x1b" not in cleaned
    assert "ನಾಳೆ meeting" in cleaned
    assert "\\[bold]" in cleaned  # Rich markup escaped, not interpreted
