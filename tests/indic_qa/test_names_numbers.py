"""Indic QA: proper names and numbers (unit tests only).

These are UNIT tests. None uses real audio, a real model, or a real
device. All fixture facts are INVENTED: the "names" are constructed
fixture labels (the word for "test" + the word for "name" in each
script), not real people, and no translation is asserted -- each test
asserts byte-identical round-trip preservation only.

Digit expectations are derived from the Unicode Standard, not from
translation: Devanagari digits are U+0966-U+096F and Kannada digits
are U+0CE6-U+0CEF, each with Numeric Digit values 0-9
(``unicodedata.digit``). The tests assert those properties, plus that
the store never silently normalises one digit script into another.
"""

from __future__ import annotations

import unicodedata

import pytest

from openjarvis.memory.store import LocalFactStore
from openjarvis.speech.kokoro_tts import KokoroTTSBackend
from openjarvis.speech.tts import TTSResult
from openjarvis.tools.storage._stubs import RetrievalResult
from openjarvis.tools.storage.chunking import chunk_text
from openjarvis.tools.storage.context import format_context

# Constructed fixture labels: "test" + "name" in each script. Invented;
# asserts identity only, never a translation or a real person's name.
NAME_CASES = [
    ("kannada", "ಪರೀಕ್ಷಾ ಹೆಸರು"),
    ("hindi", "परीक्षण नाम"),
    ("english", "Test Person"),
    ("sanskrit", "परीक्षा नाम"),
]

DEVANAGARI_DIGITS = "०१२३४५६७८९"  # U+0966-U+096F
KANNADA_DIGITS = "೦೧೨೩೪೫೬೭೮೯"  # U+0CE6-U+0CEF


@pytest.mark.parametrize("label,name", NAME_CASES)
def test_fact_store_round_trips_proper_name(tmp_path, label, name):
    """LocalFactStore preserves a proper-name fixture verbatim."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    assert store.add(name, source="indic-qa") is True
    assert [f.text for f in store.list()] == [name]


@pytest.mark.parametrize("label,name", NAME_CASES)
def test_name_survives_chunking_and_display(label, name):
    """A name survives chunk_text and the retrieval display formatter."""
    assert chunk_text(name, source="indic-qa")[0].content == name
    formatted = format_context(
        [RetrievalResult(content=name, score=1.0, source="indic-qa")]
    )
    assert name in formatted


def test_devanagari_digits_have_values_zero_to_nine():
    """Unicode: Devanagari digits U+0966-U+096F map to 0-9."""
    assert [unicodedata.digit(ch) for ch in DEVANAGARI_DIGITS] == list(range(10))
    assert [unicodedata.name(ch) for ch in DEVANAGARI_DIGITS][0].endswith("DIGIT ZERO")


def test_kannada_digits_have_values_zero_to_nine():
    """Unicode: Kannada digits U+0CE6-U+0CEF map to 0-9."""
    assert [unicodedata.digit(ch) for ch in KANNADA_DIGITS] == list(range(10))
    assert [unicodedata.name(ch) for ch in KANNADA_DIGITS][0].endswith("DIGIT ZERO")


def test_digit_scripts_have_same_values_but_are_not_equal_strings():
    """'2026', '२०२६' and '೨೦೨೬' share digit values; they are distinct text."""
    ascii_year, dev_year, kan_year = "2026", "२०२६", "೨೦೨೬"
    assert [unicodedata.digit(c) for c in dev_year] == [2, 0, 2, 6]
    assert [unicodedata.digit(c) for c in kan_year] == [2, 0, 2, 6]
    assert ascii_year != dev_year != kan_year


def test_fact_store_keeps_digit_scripts_distinct(tmp_path):
    """The store never silently normalises one digit script into another."""
    store = LocalFactStore(tmp_path / "facts.jsonl")
    store.add("Year 2026 noted", source="indic-qa")
    store.add("Year २०२६ noted", source="indic-qa")
    store.add("Year ೨೦೨೬ noted", source="indic-qa")
    assert store.count() == 3
    assert [f.text for f in store.list()] == [
        "Year 2026 noted",
        "Year २०२६ noted",
        "Year ೨೦೨೬ noted",
    ]


def test_kokoro_voice_prefix_maps_hindi():
    """Kokoro's documented prefix map: 'h' voices -> Hindi lang_code 'h'."""
    assert KokoroTTSBackend._lang_for_voice("hf_example") == "h"


def test_kokoro_has_no_kannada_or_sanskrit_voice_prefix():
    """DOCUMENTED GAP: Kokoro has no Kannada/Sanskrit lang_code on main,
    so those prefixes fall back to American English ('a'). A per-language
    voice for Kannada/Sanskrit awaits the voice branch (see
    test_voice_hooks_xfail.py)."""
    assert KokoroTTSBackend._lang_for_voice("kf_example") == "a"
    assert KokoroTTSBackend._lang_for_voice("sf_example") == "a"
    assert KokoroTTSBackend._lang_for_voice("") == "a"


def test_tts_result_save_round_trips_bytes(tmp_path):
    """TTSResult.save writes the exact audio bytes (no synthesis here)."""
    result = TTSResult(audio=b"fake-audio-bytes", format="wav", voice_id="test")
    path = result.save(tmp_path / "out.wav")
    assert path.read_bytes() == b"fake-audio-bytes"
