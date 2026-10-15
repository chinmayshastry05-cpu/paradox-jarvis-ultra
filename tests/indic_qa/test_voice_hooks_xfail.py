"""Indic QA: voice-branch hooks (xfail until the voice branch lands).

These are NOT real audio/model/device tests. The ``xfail`` tests below
pin the per-language voice behaviour that does NOT exist on ``main``
yet: they fail here (missing Kokoro voices / missing model / missing
Rust retrieval) and are expected to pass once the voice branch lands
-- ``strict=False`` so an early pass never breaks the suite. The two
passing tests pin config plumbing that already works on ``main``.

What is deliberately NOT tested here: real TTS/STT quality for any
language. Synthesising or transcribing real audio needs a model, a
microphone/speaker (or real audio files), and human or reference-based
scoring -- none of which this suite fakes. Those are documented gaps,
not passing tests.
"""

from __future__ import annotations

import io
import wave
from types import SimpleNamespace

import pytest

from openjarvis.cli._voice_chat import VoiceSession
from openjarvis.core.config import SpeechConfig
from openjarvis.speech.kokoro_tts import KokoroTTSBackend

XFAIL_VOICE_BRANCH = pytest.mark.xfail(
    strict=False,
    reason="Awaits the voice branch: per-language TTS/STT eval hooks "
    "are not in main yet. Do not fake with a stub backend.",
)


def test_speech_config_defaults_are_auto_detect():
    """SpeechConfig on main: empty language (auto-detect), kokoro TTS."""
    config = SpeechConfig()
    assert config.language == ""
    assert config.tts_backend == "kokoro"


def test_voice_session_stt_language_passthrough():
    """VoiceSession returns the configured STT language, or None."""
    kn = SimpleNamespace(speech=SimpleNamespace(language="kn"))
    assert VoiceSession(kn).get_stt_language() == "kn"
    hi = SimpleNamespace(speech=SimpleNamespace(language="hi"))
    assert VoiceSession(hi).get_stt_language() == "hi"
    blank = SimpleNamespace(speech=SimpleNamespace(language="  "))
    assert VoiceSession(blank).get_stt_language() is None


@XFAIL_VOICE_BRANCH
def test_kokoro_offers_hindi_voice():
    """Voice branch: Kokoro should offer a Hindi ('h' prefix) voice.

    On main, ``available_voices`` lists no 'h' voice even though
    ``_VOICE_PREFIX_TO_LANG`` maps 'h' -> Hindi.
    """
    voices = KokoroTTSBackend().available_voices()
    assert any(v.startswith("h") for v in voices)


@XFAIL_VOICE_BRANCH
def test_kokoro_offers_kannada_voice():
    """Voice branch: a Kannada voice.

    On main, Kokoro has no Kannada lang_code at all, so no Kannada
    voice can exist; this awaits a new backend or voice mapping.
    """
    voices = KokoroTTSBackend().available_voices()
    assert any("kannada" in v.lower() or v.startswith("k") for v in voices)


@XFAIL_VOICE_BRANCH
def test_tts_synthesizes_hindi_text():
    """Voice branch: real Hindi synthesis via the Hindi Kokoro voice.

    Fails on main (kokoro not installed / no Hindi voice). When the
    voice branch lands, this must produce real audio bytes tagged
    with lang_code 'h' -- never a stubbed byte string.
    """
    backend = KokoroTTSBackend()
    result = backend.synthesize("यह एक निर्मित परीक्षण वाक्य है", voice_id="hf_example")
    assert result.audio
    assert result.metadata.get("lang_code") == "h"


@XFAIL_VOICE_BRANCH
def test_stt_transcribes_kannada_audio():
    """Voice branch: real Faster-Whisper transcription with language='kn'.

    Input is 1s of generated silence WAV (real audio bytes, not a
    faked transcript). Fails on main (faster-whisper not installed).
    When the voice branch lands, this runs a real model; silence
    should transcribe to empty text, not raise.
    """
    from openjarvis.speech._stubs import TranscriptionResult
    from openjarvis.speech.faster_whisper import FasterWhisperBackend

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    backend = FasterWhisperBackend(model_size="tiny")
    result = backend.transcribe(buf.getvalue(), format="wav", language="kn")
    assert isinstance(result, TranscriptionResult)
    assert isinstance(result.text, str)


@XFAIL_VOICE_BRANCH
def test_bm25_retrieves_kannada_document():
    """Voice-branch-adjacent: Rust-backed BM25 retrieval with Kannada text.

    Importing the BM25 module requires the compiled ``openjarvis_rust``
    extension, which is absent in a bare checkout -- so this fails
    (ImportError) until the extension is built. When built, it must
    retrieve the Kannada document for a Kannada query.
    """
    from openjarvis.tools.storage.bm25 import BM25Memory

    backend = BM25Memory()
    backend.store("ಕಾಯಕವೇ ಕೈಲಾಸ", source="indic-qa")
    backend.store("The quick brown fox jumps over the lazy dog", source="indic-qa")
    results = backend.retrieve("ಕಾಯಕವೇ ಕೈಲಾಸ", top_k=1)
    assert results
    assert "ಕಾಯಕವೇ" in results[0].content
