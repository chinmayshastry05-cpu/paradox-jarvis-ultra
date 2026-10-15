"""Indic-language voice profiles, eval hooks, and the opt-in wake word.

Honesty rules for this module:

- A language is only ever described by what the code in this repo actually
  wires up. ``stt`` entries say "forwarded-untested" when the backend merely
  forwards a language code to a provider (faster-whisper / Deepgram) — no
  real-audio verification has happened in this environment.
- A language is "unsupported" for local TTS when no backend in this repo has
  a pipeline for it (Kannada, Sanskrit). Cloud TTS is never claimed to work
  for a language on this module's say-so: it is "untested", needs an API key,
  and is only used when the user explicitly configures that provider.
- The wake word is OFF by default and local-only: detection runs through a
  local STT backend (or an injected matcher in tests). Audio is never sent
  to any cloud provider for wake-word detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

from openjarvis.speech.voice_state import word_error_rate

__all__ = [
    "VoiceLanguage",
    "VOICE_LANGUAGES",
    "evaluate_language",
    "evaluate_transcription",
    "get_language_profile",
    "LocalWakeWordDetector",
    "supported_languages",
]


@dataclass(frozen=True)
class VoiceLanguage:
    """One language's real voice support in this repo (no aspirations)."""

    code: str  # BCP-47-ish short code used in config / evals
    name: str
    whisper_code: str  # forwarded to faster-whisper / OpenAI Whisper / Deepgram
    kokoro_lang_code: Optional[str]  # None = Kokoro has no pipeline for it
    kokoro_voice: Optional[str]  # None = repo curates no voice for it
    stt_status: str  # "forwarded-untested" — code forwards the code; unverified
    tts_status: str  # "pipeline-untested" | "no-local-pipeline"
    notes: str


VOICE_LANGUAGES: dict[str, VoiceLanguage] = {
    "en": VoiceLanguage(
        code="en",
        name="English",
        whisper_code="en",
        kokoro_lang_code="a",
        kokoro_voice="af_heart",
        stt_status="forwarded-untested",
        tts_status="pipeline-untested",
        notes="Local STT forwards 'en'; local TTS via Kokoro (af_heart).",
    ),
    "hi": VoiceLanguage(
        code="hi",
        name="Hindi",
        whisper_code="hi",
        kokoro_lang_code="h",
        kokoro_voice=None,
        stt_status="forwarded-untested",
        tts_status="pipeline-untested",
        notes=(
            "Local STT forwards 'hi'. Kokoro maps lang_code 'h', but this "
            "repo curates no Hindi voice ID — set speech.voice_id to a Hindi "
            "Kokoro voice from the installed Kokoro release; untested here."
        ),
    ),
    "kn": VoiceLanguage(
        code="kn",
        name="Kannada",
        whisper_code="kn",
        kokoro_lang_code=None,
        kokoro_voice=None,
        stt_status="forwarded-untested",
        tts_status="no-local-pipeline",
        notes=(
            "Local STT forwards 'kn' to Whisper. No local TTS pipeline: "
            "Kokoro has no Kannada pipeline, so Kannada TTS is UNSUPPORTED "
            "locally. Cloud TTS is untested and never used unless the user "
            "explicitly configures a cloud provider."
        ),
    ),
    "sa": VoiceLanguage(
        code="sa",
        name="Sanskrit",
        whisper_code="sa",
        kokoro_lang_code=None,
        kokoro_voice=None,
        stt_status="forwarded-untested",
        tts_status="no-local-pipeline",
        notes=(
            "STT forwards 'sa' to Whisper (UNTESTED — no real Sanskrit audio "
            "verified in this environment; whether the installed Whisper "
            "model handles it is unverified). TTS is UNSUPPORTED: no backend "
            "in this repo has a Sanskrit pipeline or voice. Do not claim "
            "Sanskrit speech works from mocked outputs."
        ),
    ),
}

# Long names map to codes so config/eval callers can say "kannada" or "kn".
_ALIASES = {
    "english": "en",
    "hindi": "hi",
    "kannada": "kn",
    "sanskrit": "sa",
    "saṃskṛta": "sa",
    "samskrita": "sa",
}


def get_language_profile(code: str) -> Optional[VoiceLanguage]:
    """Return the profile for ``code`` (or a long name), else None."""
    key = code.strip().lower()
    return VOICE_LANGUAGES.get(_ALIASES.get(key, key))


def supported_languages() -> list[str]:
    """Codes with a declared profile (profiles describe status, not proof)."""
    return sorted(VOICE_LANGUAGES)


def evaluate_transcription(
    reference: str,
    hypothesis: str,
    language: str,
) -> dict:
    """WER-style eval hook for one (reference, hypothesis) pair.

    Pure text comparison — no audio, no model, no network. The returned
    ``stt_status`` / ``tts_status`` come from the language profile so eval
    output never upgrades an untested path into a supported one.
    """
    profile = get_language_profile(language)
    return {
        "language": profile.code if profile else language,
        "language_name": profile.name if profile else language,
        "word_error_rate": word_error_rate(reference, hypothesis),
        "reference_words": len(reference.split()),
        "hypothesis_words": len(hypothesis.split()),
        "stt_status": profile.stt_status if profile else "unknown-language",
        "tts_status": profile.tts_status if profile else "unknown-language",
        "notes": profile.notes if profile else "No profile for this language.",
    }


def evaluate_language(
    language: str,
    pairs: Sequence[tuple[str, str]],
) -> dict:
    """Aggregate ``evaluate_transcription`` over reference/hypothesis pairs.

    Returns the mean WER plus the per-pair results. ``pairs`` must be
    non-empty; supply real reference transcripts — mocked hypotheses only
    measure the mock, never the backend.
    """
    if not pairs:
        raise ValueError("evaluate_language requires at least one pair")
    results = [evaluate_transcription(ref, hyp, language) for ref, hyp in pairs]
    wers = [r["word_error_rate"] for r in results]
    first = results[0]
    return {
        "language": first["language"],
        "language_name": first["language_name"],
        "pairs": len(pairs),
        "mean_word_error_rate": sum(wers) / len(wers),
        "worst_word_error_rate": max(wers),
        "stt_status": first["stt_status"],
        "tts_status": first["tts_status"],
        "notes": first["notes"],
        "results": results,
    }


_WORD_BOUNDARY = re.compile(r"[^a-z0-9\u0900-\u097f\u0c80-\u0cff\u1cda-\u1cff ]+")


def _normalize_phrase(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace (multi-script)."""
    lowered = text.lower()
    cleaned = _WORD_BOUNDARY.sub(" ", lowered)
    return " ".join(cleaned.split())


class LocalWakeWordDetector:
    """Opt-in, local-only wake-word detection. OFF unless enabled.

    Detection is transcript matching through a *local* STT backend (or an
    injected ``matcher`` in tests): the audio is transcribed locally and the
    phrase is looked for in the transcript. No audio is ever sent to a cloud
    provider for wake-word detection, and with no local transcriber the
    detector simply never fires (fail-closed) instead of guessing.

    This is a transcript spotter, not a low-power always-on keyword model:
    it costs one local transcription per audio window. It is not wired into
    the ``jarvis chat`` REPL loop — push-to-talk remains the interaction —
    until an always-on mic loop explicitly opts into it.
    """

    def __init__(
        self,
        *,
        phrase: str = "jarvis",
        enabled: bool = False,
        matcher: Optional[Callable[[bytes], bool]] = None,
    ) -> None:
        self._phrase = phrase
        self._enabled = enabled
        self._matcher = matcher

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def phrase(self) -> str:
        return self._phrase

    def detect(
        self,
        audio: bytes,
        *,
        transcriber: Optional[object] = None,
    ) -> bool:
        """True if the wake phrase is heard in ``audio`` (local only)."""
        if not self._enabled or not audio:
            return False
        if self._matcher is not None:
            try:
                return bool(self._matcher(audio))
            except Exception:
                return False
        if transcriber is None:
            return False
        try:
            result = transcriber.transcribe(audio, format="wav")
            transcript = getattr(result, "text", "") or ""
        except Exception:
            return False
        needle = _normalize_phrase(self._phrase)
        if not needle:
            return False
        haystack = _normalize_phrase(transcript)
        # Word-boundary match: "jarvis" must not fire on "jarvison".
        return f" {needle} " in f" {haystack} " or haystack == needle


def iter_language_profiles() -> Iterable[VoiceLanguage]:
    """All declared language profiles, sorted by code."""
    return (VOICE_LANGUAGES[code] for code in sorted(VOICE_LANGUAGES))
