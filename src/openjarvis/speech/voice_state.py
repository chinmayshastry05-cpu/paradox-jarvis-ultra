"""Push-to-talk state machine, sentence splitting, and WER for voice mode.

Small, dependency-free helpers for the ``jarvis chat --voice`` path. They
carry no audio or model code: the state machine only records legal
transitions, the splitter only cuts text, and the WER function only compares
reference/hypothesis transcripts. Real audio, STT, and TTS stay in
``voice_io`` and the speech backends.
"""

from __future__ import annotations

import re
import threading
from enum import Enum

__all__ = [
    "VoiceState",
    "PushToTalkStateMachine",
    "split_sentences",
    "word_error_rate",
]


class VoiceState(str, Enum):
    """States of one push-to-talk turn in ``jarvis chat --voice``."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


# Explicit transition table. IDLE -> SPEAKING covers a typed message in voice
# mode (no recording happened, but the reply is still spoken aloud).
_ALLOWED: dict[VoiceState, frozenset[VoiceState]] = {
    VoiceState.IDLE: frozenset({VoiceState.LISTENING, VoiceState.SPEAKING}),
    VoiceState.LISTENING: frozenset({VoiceState.PROCESSING, VoiceState.IDLE}),
    VoiceState.PROCESSING: frozenset({VoiceState.SPEAKING, VoiceState.IDLE}),
    VoiceState.SPEAKING: frozenset({VoiceState.IDLE}),
}


class PushToTalkStateMachine:
    """Explicit push-to-talk state machine with barge-in cancellation.

    The owning loop (``record_voice`` / ``speak``) performs the transitions;
    ``request_cancel`` only sets a flag that the loop polls, so a barge-in
    never tears down playback from another thread — the loop stops cleanly
    and transitions itself to IDLE.
    """

    def __init__(self) -> None:
        self._state = VoiceState.IDLE
        self._cancel = threading.Event()
        self._history: list[VoiceState] = [VoiceState.IDLE]

    @property
    def state(self) -> VoiceState:
        return self._state

    @property
    def history(self) -> list[VoiceState]:
        """States visited so far, starting with the initial IDLE."""
        return list(self._history)

    @property
    def cancel_requested(self) -> bool:
        """True once ``request_cancel`` was called and not yet cleared."""
        return self._cancel.is_set()

    def transition(self, target: VoiceState) -> None:
        """Move to ``target``; raise ValueError on an illegal transition."""
        if target not in _ALLOWED[self._state] and target is not self._state:
            raise ValueError(
                f"Illegal voice transition: {self._state.value} -> {target.value}"
            )
        if target is not self._state:
            self._state = target
            self._history.append(target)

    def to_idle(self) -> None:
        """Return to IDLE from any state (end of turn, error, barge-in)."""
        self.transition(VoiceState.IDLE)

    def request_cancel(self) -> None:
        """Flag a barge-in / cancellation; the owning loop acts on it."""
        self._cancel.set()

    def clear_cancel(self) -> None:
        """Clear the cancellation flag at the start of a new turn."""
        self._cancel.clear()

    def reset(self) -> None:
        """Return to a fresh IDLE turn (state + cancellation flag)."""
        self._cancel.clear()
        self._state = VoiceState.IDLE
        self._history.append(VoiceState.IDLE)


# Abbreviations whose trailing period must not end a sentence. Kept small and
# explicit: anything not listed here splits, which is the safe default for
# TTS (a spurious split only pauses briefly; a missed split garbles pacing).
_ABBREVIATIONS = (
    "Mr",
    "Mrs",
    "Ms",
    "Dr",
    "Prof",
    "Sr",
    "Jr",
    "St",
    "vs",
    "etc",
    "e.g",
    "i.e",
    "U.S",
    "U.K",
    "a.m",
    "p.m",
)
_ABBR_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a in _ABBREVIATIONS) + r")\.$")
# End punctuation, allowing trailing closers (quotes/parens) before the gap.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])(?=[\"'”’\)\]]*(?:\s|$))")


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences for sentence-level TTS.

    Splits on ``.!?`` followed by whitespace/end, honouring common
    abbreviations, decimals (``3.14``), ellipses, and newlines. The final
    fragment is kept even without terminal punctuation; empty input yields
    ``[]``. Markdown is passed through untouched — the TTS backend receives
    the same text ``speak`` used to send whole-response-at-once.
    """
    stripped = text.strip()
    if not stripped:
        return []
    # Newlines are hard boundaries (headings, list items, blank lines).
    chunks = re.split(r"\n+", stripped)
    sentences: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        # Walk end-punctuation candidates; skip ones that are abbreviations,
        # initialisms (U.S.), or decimals (3.14 never matches: the lookahead
        # requires whitespace/end after the period).
        parts: list[str] = []
        start = 0
        for match in _SENTENCE_END_RE.finditer(chunk):
            end = match.end()
            before = chunk[:end]
            if _ABBR_RE.search(before):
                continue
            # Swallow trailing closers so `"hi."` keeps its quote.
            while end < len(chunk) and chunk[end] in "\"'”’)]":
                end += 1
            rest = chunk[end:].lstrip()
            # Inside an initialism: "U.S." — the rest starts "S. ...".
            if re.match(r"^[A-Za-z]\.", rest):
                continue
            # A sentence ends only if the next non-space char starts a new
            # sentence (capital/digit/quote) or the chunk ends here.
            if rest and not (
                rest[0].isupper() or rest[0].isdigit() or rest[0] in "\"'“‘("
            ):
                continue
            parts.append(chunk[start:end].strip())
            start = end
        tail = chunk[start:].strip()
        if tail:
            parts.append(tail)
        # A bare list marker ("1.") is not a sentence — speak it with the
        # item that follows instead of as a lone utterance.
        merged: list[str] = []
        for part in parts:
            if merged and re.fullmatch(r"\d+[.)]", merged[-1]):
                merged[-1] = f"{merged[-1]} {part}"
            else:
                merged.append(part)
        sentences.extend(p for p in merged if p)
    return sentences


_WORD_RE = re.compile(r"[^\w\s']+", re.UNICODE)


def _words(text: str) -> list[str]:
    """Lowercased, punctuation-stripped words (WER normalisation)."""
    return _WORD_RE.sub(" ", text.lower()).split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word error rate: word-level Levenshtein edits / reference words.

    Returns 0.0 for identical transcripts, 1.0 when the reference is empty
    but the hypothesis is not (and 0.0 when both are empty). Values above
    1.0 are possible when the hypothesis has more insertions than the
    reference has words — that is the standard WER definition, not a bug.
    """
    ref = _words(reference)
    hyp = _words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    # DP over word edits; only two rows are needed.
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + cost,  # substitution
                )
            )
        previous = current
    return previous[len(hyp)] / len(ref)
