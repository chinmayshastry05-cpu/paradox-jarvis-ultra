"""Voice improvements: push-to-talk state machine, sentence-level TTS,
barge-in, opt-in local wake word, and Indic-language eval hooks.

All tests here are unit/mocked: no microphone, speaker, model, or network is
touched. Real audio/model/device behaviour is explicitly NOT covered.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from openjarvis.cli._voice_chat import VoiceSession, record_voice, speak
from openjarvis.core.config import JarvisConfig, SpeechConfig
from openjarvis.speech.indic import (
    LocalWakeWordDetector,
    evaluate_language,
    evaluate_transcription,
    get_language_profile,
)
from openjarvis.speech.voice_state import (
    PushToTalkStateMachine,
    VoiceState,
    split_sentences,
    word_error_rate,
)

# ---------------------------------------------------------------- state machine


def test_state_machine_happy_path() -> None:
    machine = PushToTalkStateMachine()
    machine.transition(VoiceState.LISTENING)
    machine.transition(VoiceState.PROCESSING)
    machine.transition(VoiceState.SPEAKING)
    machine.transition(VoiceState.IDLE)
    assert machine.state is VoiceState.IDLE
    assert machine.history == [
        VoiceState.IDLE,
        VoiceState.LISTENING,
        VoiceState.PROCESSING,
        VoiceState.SPEAKING,
        VoiceState.IDLE,
    ]


def test_state_machine_idle_to_speaking_for_typed_messages() -> None:
    machine = PushToTalkStateMachine()
    machine.transition(VoiceState.SPEAKING)
    assert machine.state is VoiceState.SPEAKING


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        (VoiceState.IDLE, VoiceState.PROCESSING),
        (VoiceState.LISTENING, VoiceState.SPEAKING),
        (VoiceState.SPEAKING, VoiceState.LISTENING),
        (VoiceState.PROCESSING, VoiceState.LISTENING),
    ],
)
def test_state_machine_illegal_transitions_raise(from_state, to_state) -> None:
    machine = PushToTalkStateMachine()
    # Reach from_state via a legal path (IDLE cannot jump to PROCESSING).
    path = {
        VoiceState.LISTENING: [VoiceState.LISTENING],
        VoiceState.PROCESSING: [VoiceState.LISTENING, VoiceState.PROCESSING],
        VoiceState.SPEAKING: [
            VoiceState.LISTENING,
            VoiceState.PROCESSING,
            VoiceState.SPEAKING,
        ],
    }.get(from_state, [])
    for step in path:
        machine.transition(step)
    with pytest.raises(ValueError, match="Illegal voice transition"):
        machine.transition(to_state)


def test_state_machine_cancel_flag_and_reset() -> None:
    machine = PushToTalkStateMachine()
    assert not machine.cancel_requested
    machine.request_cancel()
    assert machine.cancel_requested
    machine.clear_cancel()
    assert not machine.cancel_requested
    machine.transition(VoiceState.LISTENING)
    machine.request_cancel()
    machine.reset()
    assert machine.state is VoiceState.IDLE
    assert not machine.cancel_requested


def test_state_machine_same_state_is_a_noop() -> None:
    machine = PushToTalkStateMachine()
    machine.transition(VoiceState.IDLE)
    assert machine.history == [VoiceState.IDLE]


# ---------------------------------------------------------------- sentence split


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello world. How are you? Fine!", ["Hello world.", "How are you?", "Fine!"]),
        (
            "Dr. Smith went to Washington. He stayed.",
            ["Dr. Smith went to Washington.", "He stayed."],
        ),
        ("The value is 3.14. Next sentence.", ["The value is 3.14.", "Next sentence."]),
        ("U.S. Army marches. Onward.", ["U.S. Army marches.", "Onward."]),
        (
            'He said "hi." Then he left.',
            ['He said "hi."', "Then he left."],
        ),
        ("Wait... Really? Yes!", ["Wait...", "Really?", "Yes!"]),
        ("", []),
        ("   ", []),
        ("No punctuation", ["No punctuation"]),
        ("First line\nSecond line", ["First line", "Second line"]),
        (
            "e.g. this is an example. Next.",
            ["e.g. this is an example.", "Next."],
        ),
        (
            "1. Do this. 2. Do that.",
            ["1. Do this.", "2. Do that."],
        ),
    ],
)
def test_split_sentences(text, expected) -> None:
    assert split_sentences(text) == expected


# ---------------------------------------------------------------- WER


@pytest.mark.parametrize(
    "reference,hypothesis,expected",
    [
        ("hello world", "hello world", 0.0),
        ("hello world", "hello world!", 0.0),  # punctuation normalised
        ("Hello World", "hello world", 0.0),  # case normalised
        ("the cat sat", "the dog sat", 1 / 3),
        ("a b", "a b c", 0.5),  # one insertion
        ("a b c", "a b", 1 / 3),  # one deletion
        ("", "", 0.0),
        ("", "hi", 1.0),
    ],
)
def test_word_error_rate(reference, hypothesis, expected) -> None:
    assert word_error_rate(reference, hypothesis) == pytest.approx(expected)


# ---------------------------------------------------------------- Indic profiles


def test_language_profiles_are_honest_about_support() -> None:
    kannada = get_language_profile("kn")
    assert kannada is not None
    assert kannada.tts_status == "no-local-pipeline"  # UNSUPPORTED locally
    assert kannada.stt_status == "forwarded-untested"

    sanskrit = get_language_profile("sa")
    assert sanskrit is not None
    assert sanskrit.tts_status == "no-local-pipeline"  # UNSUPPORTED
    assert sanskrit.stt_status == "forwarded-untested"  # UNTESTED, never claimed

    hindi = get_language_profile("hi")
    assert hindi is not None
    assert hindi.kokoro_lang_code == "h"
    assert hindi.kokoro_voice is None  # no curated Hindi voice ID in this repo

    english = get_language_profile("en")
    assert english is not None
    assert english.kokoro_voice == "af_heart"


def test_language_profile_aliases_and_unknown() -> None:
    assert get_language_profile("kannada").code == "kn"
    assert get_language_profile("sanskrit").code == "sa"
    assert get_language_profile("xx") is None


def test_evaluate_transcription_carries_profile_status() -> None:
    result = evaluate_transcription("hello world", "hello world", "en")
    assert result["word_error_rate"] == 0.0
    assert result["stt_status"] == "forwarded-untested"
    assert result["language"] == "en"


def test_evaluate_language_aggregates_pairs() -> None:
    result = evaluate_language("kn", [("a b", "a b"), ("a b c", "a x c")])
    assert result["pairs"] == 2
    assert result["mean_word_error_rate"] == pytest.approx((0.0 + 1 / 3) / 2)
    assert result["tts_status"] == "no-local-pipeline"


def test_evaluate_language_requires_pairs() -> None:
    with pytest.raises(ValueError, match="at least one pair"):
        evaluate_language("en", [])


# ---------------------------------------------------------------- wake word


class _FakeTranscriber:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[bytes] = []

    def transcribe(self, audio: bytes, **kwargs):
        self.calls.append(audio)
        return SimpleNamespace(text=self._text)


def test_wake_word_off_by_default() -> None:
    assert SpeechConfig().wake_word_enabled is False
    assert SpeechConfig().wake_word_phrase == "jarvis"
    detector = LocalWakeWordDetector()
    assert not detector.enabled
    assert detector.detect(b"audio", transcriber=_FakeTranscriber("jarvis")) is False


def test_wake_word_matches_transcript_locally() -> None:
    detector = LocalWakeWordDetector(enabled=True, phrase="jarvis")
    assert detector.detect(b"audio", transcriber=_FakeTranscriber("hey jarvis listen"))
    assert not detector.detect(b"audio", transcriber=_FakeTranscriber("nothing here"))
    # Word boundary: "jarvison" is not the wake word.
    assert not detector.detect(b"audio", transcriber=_FakeTranscriber("jarvison"))


def test_wake_word_never_fires_without_local_transcriber() -> None:
    detector = LocalWakeWordDetector(enabled=True, phrase="jarvis")
    assert detector.detect(b"audio") is False
    assert detector.detect(b"") is False


def test_wake_word_injected_matcher() -> None:
    detector = LocalWakeWordDetector(
        enabled=True, matcher=lambda audio: audio == b"wake"
    )
    assert detector.detect(b"wake")
    assert not detector.detect(b"other")


def test_voice_session_check_wake_word(monkeypatch) -> None:
    config = JarvisConfig()
    config.speech.wake_word_enabled = True
    session = VoiceSession(config)
    transcriber = _FakeTranscriber("ok jarvis go")
    monkeypatch.setattr(
        "openjarvis.speech._discovery.get_speech_backend",
        lambda config: transcriber,
    )
    assert session.check_wake_word(b"audio") is True
    assert transcriber.calls == [b"audio"]

    disabled = VoiceSession(JarvisConfig())
    assert disabled.check_wake_word(b"audio") is False


# ---------------------------------------------------------------- speak / record


@dataclass
class _Speech:
    tts_backend: str = "kokoro"
    voice_id: str = "bm_george"
    voice_speed: float = 1.0


@dataclass
class _Config:
    speech: _Speech


def _session(**kwargs) -> VoiceSession:
    return VoiceSession(config=_Config(speech=_Speech(**kwargs)))


class _Backend:
    def __init__(self, backend_id: str) -> None:
        self.backend_id = backend_id

    def health(self) -> bool:
        return True


class _Console:
    def print(self, message) -> None:
        pass


def _patch_tts(monkeypatch, backend_cls, played) -> None:
    from openjarvis.core.registry import TTSRegistry

    monkeypatch.setattr(TTSRegistry, "contains", lambda key: True)
    monkeypatch.setattr(TTSRegistry, "get", lambda key: lambda: backend_cls(key))
    monkeypatch.setattr(
        "openjarvis.speech.voice_io.play_wav",
        lambda audio, **kwargs: played.append(audio),
    )


def test_speak_synthesizes_sentence_by_sentence(monkeypatch) -> None:
    from openjarvis.speech.tts import TTSResult

    spoken: list[tuple[str, str]] = []
    played: list[bytes] = []

    class Backend(_Backend):
        def synthesize(self, text, **kwargs):
            spoken.append((self.backend_id, text))
            return TTSResult(audio=b"wav", sample_rate=24000, format="wav")

    _patch_tts(monkeypatch, Backend, played)
    session = _session()

    speak(
        "First sentence. Second sentence! Third?",
        _Console(),
        session,
        allow_barge_in=False,
    )

    assert spoken == [
        ("kokoro", "First sentence."),
        ("kokoro", "Second sentence!"),
        ("kokoro", "Third?"),
    ]
    assert played == [b"wav", b"wav", b"wav"]
    assert session.state_machine.state is VoiceState.IDLE
    assert session.state_machine.history[-2:] == [
        VoiceState.SPEAKING,
        VoiceState.IDLE,
    ]


def test_speak_barge_in_stops_remaining_sentences(monkeypatch) -> None:
    from openjarvis.speech.tts import TTSResult

    spoken: list[str] = []
    played: list[bytes] = []
    session = _session()

    class Backend(_Backend):
        def synthesize(self, text, **kwargs):
            spoken.append(text)
            return TTSResult(audio=b"wav", sample_rate=24000, format="wav")

    def _play(audio, **kwargs):
        played.append(audio)
        session.request_barge_in()  # user interrupts during first sentence

    from openjarvis.core.registry import TTSRegistry

    monkeypatch.setattr(TTSRegistry, "contains", lambda key: True)
    monkeypatch.setattr(TTSRegistry, "get", lambda key: lambda: Backend(key))
    monkeypatch.setattr("openjarvis.speech.voice_io.play_wav", _play)

    speak(
        "First sentence. Second sentence. Third sentence.",
        _Console(),
        session,
        allow_barge_in=False,
    )

    assert spoken == ["First sentence."]
    assert played == [b"wav"]
    assert session.state_machine.state is VoiceState.IDLE


def test_speak_fallback_resumes_remaining_sentences_only(monkeypatch) -> None:
    from openjarvis.speech.tts import TTSResult

    spoken: list[tuple[str, str]] = []
    played: list[bytes] = []

    class Backend(_Backend):
        def synthesize(self, text, **kwargs):
            spoken.append((self.backend_id, text))
            if self.backend_id == "openai_tts" and text == "Second sentence.":
                raise RuntimeError("provider unavailable")
            return TTSResult(audio=b"wav", sample_rate=24000, format="wav")

    _patch_tts(monkeypatch, Backend, played)
    session = _session(tts_backend="openai_tts", voice_id="nova")

    speak(
        "First sentence. Second sentence. Third sentence.",
        _Console(),
        session,
        allow_barge_in=False,
    )

    # Sentence 1 is never replayed after the fallback.
    assert spoken == [
        ("openai_tts", "First sentence."),
        ("openai_tts", "Second sentence."),
        ("kokoro", "Second sentence."),
        ("kokoro", "Third sentence."),
    ]
    assert played == [b"wav", b"wav", b"wav"]


def test_speak_empty_text_touches_no_backend(monkeypatch) -> None:
    from openjarvis.core.registry import TTSRegistry

    calls: list[str] = []
    monkeypatch.setattr(TTSRegistry, "contains", lambda key: True)

    def _no_get(key):
        raise AssertionError("must not resolve a TTS backend for empty text")

    monkeypatch.setattr(TTSRegistry, "get", _no_get)
    monkeypatch.setattr(
        "openjarvis.speech.voice_io.play_wav",
        lambda audio, **kwargs: calls.append("play"),
    )
    speak("", _Console(), _session(), allow_barge_in=False)
    assert calls == []


def test_record_voice_returns_machine_to_idle(monkeypatch) -> None:
    backend = SimpleNamespace(
        transcribe=lambda audio, **kwargs: SimpleNamespace(text="hello")
    )
    monkeypatch.setattr(
        "openjarvis.speech._discovery.get_speech_backend",
        lambda config: backend,
    )
    monkeypatch.setattr(
        "openjarvis.speech.voice_io.record_until_silence",
        lambda: b"wav",
    )
    session = VoiceSession(JarvisConfig())
    assert record_voice(_Console(), session) == "hello"
    assert session.state_machine.state is VoiceState.IDLE
    assert session.state_machine.history == [
        VoiceState.IDLE,
        VoiceState.LISTENING,
        VoiceState.PROCESSING,
        VoiceState.IDLE,
    ]


# ---------------------------------------------------------------- play_wav stop


class _FakeSoundFile:
    def read(self, buf, dtype="float32"):
        return b"data", 24000


def _install_playback(monkeypatch, *, blocking: bool) -> SimpleNamespace:
    stopped = threading.Event()
    calls: list[str] = []

    class FakeSD:
        def play(self, data, sr):
            calls.append("play")

        def wait(self):
            calls.append("wait")
            if blocking:
                stopped.wait(timeout=5)

        def stop(self):
            calls.append("stop")
            stopped.set()

    fake_sd = FakeSD()
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "soundfile", _FakeSoundFile())
    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace())
    return SimpleNamespace(calls=calls, sd=fake_sd)


def test_play_wav_stops_when_should_stop_turns_true(monkeypatch) -> None:
    from openjarvis.speech.voice_io import play_wav

    tracker = _install_playback(monkeypatch, blocking=True)
    play_wav(b"fake-wav", should_stop=lambda: True)
    assert "stop" in tracker.calls
    assert "wait" in tracker.calls


def test_play_wav_without_stop_plays_through(monkeypatch) -> None:
    from openjarvis.speech.voice_io import play_wav

    tracker = _install_playback(monkeypatch, blocking=False)
    play_wav(b"fake-wav", should_stop=lambda: False)
    assert tracker.calls == ["play", "wait"]


def test_play_wav_without_should_stop_unchanged(monkeypatch) -> None:
    from openjarvis.speech.voice_io import play_wav

    tracker = _install_playback(monkeypatch, blocking=False)
    play_wav(b"fake-wav")
    assert tracker.calls == ["play", "wait"]
