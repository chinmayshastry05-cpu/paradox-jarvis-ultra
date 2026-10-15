"""GuardrailsEngine — security-aware inference engine wrapper."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional, Sequence

from openjarvis.core.events import EventBus, EventType
from openjarvis.core.types import Message
from openjarvis.engine._stubs import InferenceEngine, StreamChunk
from openjarvis.security._stubs import BaseScanner
from openjarvis.security.scanner import PIIScanner, SecretScanner
from openjarvis.security.types import RedactionMode, ScanResult


class SecurityBlockError(Exception):
    """Raised when mode is BLOCK and security findings are detected."""


# Streaming output is scanned BEFORE delivery, not after. Tokens are
# buffered and only released once the scan covering them has passed.
# _STREAM_HOLDBACK_CHARS of trailing text is always held back: a secret
# split across a flush boundary is only released once a later scan has
# seen it whole. _STREAM_FLUSH_CHARS bounds the buffer so a long
# secret-free stretch still streams promptly.
_STREAM_FLUSH_CHARS = 1024
_STREAM_HOLDBACK_CHARS = 256
_STREAM_FLUSH_SUFFIXES = (". ", "! ", "? ", ".\n", "!\n", "?\n", "\n\n")


class GuardrailsEngine(InferenceEngine):
    """Wraps an existing ``InferenceEngine`` with security scanning.

    Not registered in ``EngineRegistry`` — instantiated dynamically to wrap
    any engine at runtime.

    Parameters
    ----------
    engine:
        The wrapped inference engine.
    scanners:
        List of scanners to run.  Defaults to ``SecretScanner`` + ``PIIScanner``.
    mode:
        Action taken on findings: WARN, REDACT, or BLOCK.
    scan_input:
        Whether to scan input messages.
    scan_output:
        Whether to scan output content.
    bus:
        Optional event bus for publishing security events.
    """

    def __init__(
        self,
        engine: InferenceEngine,
        *,
        scanners: Optional[List[BaseScanner]] = None,
        mode: RedactionMode = RedactionMode.WARN,
        scan_input: bool = True,
        scan_output: bool = True,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._engine = engine
        self._scanners: List[BaseScanner] = (
            scanners
            if scanners is not None
            else [
                SecretScanner(),
                PIIScanner(),
            ]
        )
        self._mode = mode
        self._scan_input = scan_input
        self._scan_output = scan_output
        self._bus = bus

    # -- properties ----------------------------------------------------------

    @property
    def engine_id(self) -> str:  # type: ignore[override]
        """Delegate to the wrapped engine."""
        return self._engine.engine_id

    # -- scanning helpers ----------------------------------------------------

    def _scan_text(self, text: str) -> ScanResult:
        """Run all scanners on *text* and merge findings."""
        merged = ScanResult()
        for scanner in self._scanners:
            result = scanner.scan(text)
            merged.findings.extend(result.findings)
        return merged

    def _redact_text(self, text: str) -> str:
        """Run all scanners' redact() on *text*."""
        result = text
        for scanner in self._scanners:
            result = scanner.redact(result)
        return result

    def _handle_findings(
        self,
        text: str,
        result: ScanResult,
        direction: str,
    ) -> str:
        """Apply the configured mode to findings.

        Parameters
        ----------
        text:
            The original text.
        result:
            Scan result containing findings.
        direction:
            ``"input"`` or ``"output"`` — used in event data.

        Returns
        -------
        str
            Possibly modified text (unchanged for WARN, redacted for REDACT).

        Raises
        ------
        SecurityBlockError
            If mode is BLOCK.
        """
        finding_dicts = [
            {
                "pattern": f.pattern_name,
                "threat": f.threat_level.value,
                "description": f.description,
            }
            for f in result.findings
        ]

        if self._mode == RedactionMode.WARN:
            if self._bus:
                self._bus.publish(
                    EventType.SECURITY_ALERT,
                    {
                        "direction": direction,
                        "findings": finding_dicts,
                        "mode": "warn",
                    },
                )
            return text

        if self._mode == RedactionMode.REDACT:
            if self._bus:
                self._bus.publish(
                    EventType.SECURITY_ALERT,
                    {
                        "direction": direction,
                        "findings": finding_dicts,
                        "mode": "redact",
                    },
                )
            return self._redact_text(text)

        # BLOCK mode
        if self._bus:
            self._bus.publish(
                EventType.SECURITY_BLOCK,
                {
                    "direction": direction,
                    "findings": finding_dicts,
                    "mode": "block",
                },
            )
        raise SecurityBlockError(
            f"Security scan blocked {direction}: "
            f"{len(result.findings)} finding(s) detected"
        )

    def _prepare_messages(self, messages: Sequence[Message]) -> Sequence[Message]:
        """Apply input policy without mutating the caller's messages."""
        # Scan input messages
        if self._scan_input:
            processed = list(messages)
            for i, msg in enumerate(processed):
                if msg.content:
                    result = self._scan_text(msg.content)
                    if not result.clean:
                        processed[i] = Message(
                            role=msg.role,
                            content=self._handle_findings(
                                msg.content,
                                result,
                                "input",
                            ),
                            name=msg.name,
                            tool_calls=msg.tool_calls,
                            tool_call_id=msg.tool_call_id,
                            metadata=msg.metadata,
                            images=msg.images,
                        )
            return processed

        return messages

    # -- InferenceEngine interface -------------------------------------------

    def generate(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Scan input, call wrapped engine, scan output."""
        messages = self._prepare_messages(messages)

        # Call wrapped engine
        response = self._engine.generate(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        # Scan output
        if self._scan_output:
            content = response.get("content", "")
            if content:
                result = self._scan_text(content)
                if not result.clean:
                    response["content"] = self._handle_findings(
                        content, result, "output"
                    )

        return response

    def _scan_and_release(self, buf: str, *, final: bool) -> tuple[str, str]:
        """Scan *buf* and split it into (release_now, keep_buffered).

        Nothing is released until the scan covering it has passed, so a
        secret is redacted/blocked before delivery, never after. The
        trailing holdback stays buffered so a secret split across a
        flush boundary is caught whole by a later scan. In BLOCK mode
        this raises :class:`SecurityBlockError` before any of *buf* is
        released (previously released text was already scanned clean).
        """
        if not buf:
            return "", ""
        if not self._scan_output:
            return buf, ""
        if not final:
            # Nothing releasable yet: hold the whole buffer for a later
            # scan instead of scanning (and alerting on) the same prefix
            # on every incoming token.
            if len(buf) <= _STREAM_HOLDBACK_CHARS and not buf.endswith(
                _STREAM_FLUSH_SUFFIXES
            ):
                return "", buf
            if len(buf) < _STREAM_FLUSH_CHARS and not buf.endswith(
                _STREAM_FLUSH_SUFFIXES
            ):
                return "", buf
        result = self._scan_text(buf)
        if not result.clean:
            # WARN returns buf unchanged (with an alert); REDACT redacts;
            # BLOCK raises before anything in buf is delivered.
            buf = self._handle_findings(buf, result, "output")
        if final:
            return buf, ""
        if len(buf) <= _STREAM_HOLDBACK_CHARS:
            return "", buf
        return buf[:-_STREAM_HOLDBACK_CHARS], buf[-_STREAM_HOLDBACK_CHARS:]

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Scan input, then buffer + scan output before yielding tokens."""
        messages = self._prepare_messages(messages)
        buf = ""
        async for token in self._engine.stream(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            buf += token
            release, buf = self._scan_and_release(buf, final=False)
            if release:
                yield release
        release, _ = self._scan_and_release(buf, final=True)
        if release:
            yield release

    async def stream_full(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator["StreamChunk"]:
        """Scan input, then buffer + scan content before yielding chunks."""
        from dataclasses import replace as _replace

        messages = self._prepare_messages(messages)
        buf = ""
        async for chunk in self._engine.stream_full(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            if chunk.content:
                buf += chunk.content
                release, buf = self._scan_and_release(buf, final=False)
                if release:
                    yield StreamChunk(content=release)
                # A chunk carrying tool_calls/finish alongside content
                # must not lose its non-content fields: flush the
                # buffered content (scanned), then forward the rest.
                if (
                    chunk.tool_calls is not None
                    or chunk.finish_reason is not None
                    or chunk.usage is not None
                    or chunk.content_blocks is not None
                    or chunk.tool_results is not None
                ):
                    release, buf = self._scan_and_release(buf, final=True)
                    if release:
                        yield StreamChunk(content=release)
                    yield _replace(chunk, content=None)
                continue
            # Non-content chunks (tool calls, finish) pass through, but
            # only after flushing buffered content first so stream order
            # is preserved.
            release, buf = self._scan_and_release(buf, final=True)
            if release:
                yield StreamChunk(content=release)
            yield chunk
        release, _ = self._scan_and_release(buf, final=True)
        if release:
            yield StreamChunk(content=release)

    def list_models(self) -> List[str]:
        """Delegate to wrapped engine."""
        return self._engine.list_models()

    def health(self) -> bool:
        """Delegate to wrapped engine."""
        return self._engine.health()

    def close(self) -> None:
        """Release resources held by the wrapped engine."""
        self._engine.close()


__all__ = ["GuardrailsEngine", "SecurityBlockError"]
