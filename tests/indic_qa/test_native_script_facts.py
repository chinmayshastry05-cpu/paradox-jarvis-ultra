"""Indic QA: native-script text paths (unit / mocked tests only).

These are UNIT and MOCKED tests. None of them uses real audio, a real
model, or a real device: the "engine" below is a stub whose ``generate``
return value is supplied by the test, and every other assertion runs
against pure-Python text/storage code on ``main``.

Source rule for expected strings: every non-ASCII expected string in
this module is either
  (a) a cited, well-known source string -- the test asserts
      byte-identical round-trip preservation ONLY, never a translation
      or a meaning; or
  (b) a constructed fixture string -- the test asserts byte-identical
      round-trip ONLY, never grammatical correctness or translation.
No translation is asserted anywhere in this module.

Cited sources (preservation only):
  - Sanskrit "सत्यमेव जयते" -- Mundaka Upanishad 3.1.6; India's
    national motto.
  - Kannada "ಕಾಯಕವೇ ಕೈಲಾಸ" -- vachana attributed to Basavanna
    (12th century).
All other strings are constructed fixtures.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from openjarvis.memory.extractor import FactExtractor
from openjarvis.memory.store import (
    Fact,
    LocalFactStore,
    load_configured_facts,
)
from openjarvis.tools.storage.chunking import ChunkConfig, chunk_text
from openjarvis.tools.storage.context import build_context_message

# (language label, fixture string, source note)
NATIVE_CASES = [
    ("kannada", "ಕಾಯಕವೇ ಕೈಲಾಸ", "cited: vachana attributed to Basavanna"),
    ("hindi", "यह एक निर्मित परीक्षण वाक्य है", "constructed fixture"),
    ("english", "The quick brown fox jumps over the lazy dog", "constructed fixture"),
    ("sanskrit", "सत्यमेव जयते", "cited: Mundaka Upanishad 3.1.6"),
]


@pytest.mark.parametrize("language,text,_source", NATIVE_CASES)
def test_fact_store_round_trips_native_script(tmp_path, language, text, _source):
    """LocalFactStore preserves each language's native script verbatim."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    assert store.add(text, source="indic-qa") is True
    facts = store.list()
    assert [f.text for f in facts] == [text]
    assert store.count() == 1


def test_fact_store_persists_native_script_as_utf8(tmp_path):
    """On-disk JSONL keeps native script as UTF-8, not ASCII escapes."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    store.add("ಕಾಯಕವೇ ಕೈಲಾಸ", source="indic-qa")
    raw = (tmp_path / "facts.jsonl").read_bytes()
    assert "ಕಾಯಕವೇ ಕೈಲಾಸ".encode("utf-8") in raw
    assert b"\\u0c95" not in raw  # no ASCII-escaped Kannada


def test_fact_store_dedupes_exact_duplicate_indic_text(tmp_path):
    """Adding the same native-script fact twice stores it once."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    assert store.add("सत्यमेव जयते", source="indic-qa") is True
    assert store.add("सत्यमेव जयते", source="indic-qa") is False
    assert store.count() == 1


def test_fact_store_english_case_dedupe_still_works(tmp_path):
    """Sanity: the existing case-insensitive dedupe still applies."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    assert store.add("Prefers concise answers") is True
    assert store.add("prefers concise answers") is False
    assert store.count() == 1


@pytest.mark.parametrize("language,text,_source", NATIVE_CASES)
def test_chunk_text_single_chunk_preserves_native_script(language, text, _source):
    """chunk_text with a generous window returns the text unchanged."""
    chunks = chunk_text(text, source="indic-qa")
    assert len(chunks) == 1
    assert chunks[0].content == text


def test_chunk_text_multi_chunk_covers_all_indic_tokens():
    """Small windows split Indic text without losing any token."""
    text = " ".join(["ಕಾಯಕವೇ ಕೈಲಾಸ"] * 20)  # constructed repetition
    chunks = chunk_text(
        text, source="indic-qa", config=ChunkConfig(chunk_size=5, chunk_overlap=1)
    )
    assert len(chunks) > 1
    assert all(len(c.content.split()) <= 5 for c in chunks)
    assert all(c.content for c in chunks)
    covered = set()
    for chunk in chunks:
        covered.update(chunk.content.split())
    assert covered == set(text.split())


@pytest.mark.parametrize("language,text,_source", NATIVE_CASES)
def test_context_message_includes_native_script_fact(language, text, _source):
    """build_context_message carries native-script facts into the prompt."""
    message = build_context_message([], [Fact(text=text, source="indic-qa")])
    assert text in message.content


def test_extractor_parses_indic_facts_from_mocked_engine():
    """FactExtractor returns mocked-engine Indic facts verbatim (no model)."""
    engine = MagicMock()
    engine.generate.return_value = {"content": '["ಕಾಯಕವೇ ಕೈಲಾಸ", "सत्यमेव जयते"]'}
    extractor = FactExtractor(engine, model="mock-model")
    facts = extractor.extract("constructed user turn", "constructed reply")
    assert facts == ["ಕಾಯಕವೇ ಕೈಲಾಸ", "सत्यमेव जयते"]


def test_extractor_never_raises_when_engine_fails():
    """A failing engine degrades to 'no facts', never an exception."""
    engine = MagicMock()
    engine.generate.side_effect = RuntimeError("engine unavailable")
    extractor = FactExtractor(engine, model="mock-model")
    assert extractor.extract("test input", "") == []


def test_load_configured_facts_returns_indic_facts(tmp_path):
    """load_configured_facts reads native-script facts back via config."""
    path = tmp_path / "facts.jsonl"
    store = LocalFactStore(path)
    store.add("यह एक निर्मित परीक्षण वाक्य है", source="indic-qa")
    config = SimpleNamespace(
        memory=SimpleNamespace(
            enabled=True, backend="local", facts_path=str(path), max_facts=1000
        )
    )
    facts = load_configured_facts(config)
    assert [f.text for f in facts] == ["यह एक निर्मित परीक्षण वाक्य है"]


def test_load_configured_facts_disabled_returns_empty(tmp_path):
    """Memory disabled -> no facts leak into model-facing paths."""
    config = SimpleNamespace(memory=SimpleNamespace(enabled=False))
    assert load_configured_facts(config) == []


def test_fact_store_clear_removes_native_script_facts(tmp_path):
    """clear() removes Indic facts and the backing file."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    store.add("ಕಾಯಕವೇ ಕೈಲಾಸ", source="indic-qa")
    assert store.clear() == 1
    assert store.count() == 0
    assert store.list() == []
