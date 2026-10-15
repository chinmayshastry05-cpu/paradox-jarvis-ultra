"""End-to-end security tests for the confirmation gate, canonical paths,
shell opt-in, keychain vault, and pre-delivery output scanning.

Each test attacks one bypass: approval reuse, argument tampering,
expired/revoked approvals, symlink escapes, shell without opt-in,
keychain-unavailable vault use, and secrets split across stream chunks.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from openjarvis.core.types import Message, Role, ToolCall, ToolResult
from openjarvis.security._stubs import BaseScanner
from openjarvis.security.canonical_path import is_within, resolve_within
from openjarvis.security.confirmation import ConfirmationGate, canonical_arguments
from openjarvis.security.guardrails import GuardrailsEngine, SecurityBlockError
from openjarvis.security.keychain import (
    Keychain,
    KeychainUnavailable,
    get_default_backend,
)
from openjarvis.security.types import (
    RedactionMode,
    ScanFinding,
    ScanResult,
    ThreatLevel,
)
from openjarvis.tools._stubs import BaseTool, ToolExecutor, ToolSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DangerousTool(BaseTool):
    tool_id = "dangerous"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="dangerous",
            description="Requires confirmation.",
            requires_confirmation=True,
        )

    def execute(self, **params: Any) -> ToolResult:
        return ToolResult(tool_name="dangerous", content="executed!", success=True)


class _SafeTool(BaseTool):
    tool_id = "safe"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="safe", description="No confirmation.", requires_confirmation=False
        )

    def execute(self, **params: Any) -> ToolResult:
        return ToolResult(tool_name="safe", content="safe result", success=True)


class _FakeSecretScanner(BaseScanner):
    """Flags the marker SECRET-MARKER anywhere it appears, even split."""

    scanner_id = "fake-secrets"
    MARKER = "SECRET-MARKER-12345"

    def scan(self, text: str) -> ScanResult:
        idx = text.find(self.MARKER)
        if idx < 0:
            return ScanResult()
        return ScanResult(
            findings=[
                ScanFinding(
                    pattern_name="fake_secret",
                    matched_text=self.MARKER,
                    threat_level=ThreatLevel.CRITICAL,
                    start=idx,
                    end=idx + len(self.MARKER),
                    description="Fake secret marker",
                )
            ]
        )

    def redact(self, text: str) -> str:
        return text.replace(self.MARKER, "[REDACTED:fake_secret]")


class _FakeEngine:
    """Minimal async engine yielding canned tokens."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self.engine_id = "fake"

    async def stream(self, messages, **kwargs):
        for token in self._tokens:
            yield token

    async def stream_full(self, messages, **kwargs):
        from openjarvis.engine._stubs import StreamChunk

        for token in self._tokens:
            yield StreamChunk(content=token)

    def generate(self, messages, **kwargs):
        return {"content": "".join(self._tokens)}


# ---------------------------------------------------------------------------
# ConfirmationGate
# ---------------------------------------------------------------------------


class TestConfirmationGate:
    def test_grant_consume_once(self) -> None:
        gate = ConfirmationGate()
        approval = gate.grant("dangerous", {"action": "delete"})
        assert gate.consume(approval.token, "dangerous", {"action": "delete"}) is True

    def test_reuse_rejected(self) -> None:
        gate = ConfirmationGate()
        approval = gate.grant("dangerous", {"action": "delete"})
        assert gate.consume(approval.token, "dangerous", {"action": "delete"}) is True
        assert gate.consume(approval.token, "dangerous", {"action": "delete"}) is False

    def test_argument_tampering_rejected(self) -> None:
        gate = ConfirmationGate()
        approval = gate.grant("dangerous", {"action": "delete", "target": "a"})
        assert (
            gate.consume(
                approval.token, "dangerous", {"action": "delete", "target": "b"}
            )
            is False
        )
        # The untampered approval is still valid afterwards.
        assert (
            gate.consume(
                approval.token, "dangerous", {"action": "delete", "target": "a"}
            )
            is True
        )

    def test_wrong_tool_rejected(self) -> None:
        gate = ConfirmationGate()
        approval = gate.grant("dangerous", {"action": "delete"})
        assert gate.consume(approval.token, "other_tool", {"action": "delete"}) is False

    def test_expired_rejected(self) -> None:
        gate = ConfirmationGate()
        approval = gate.grant("dangerous", {"action": "delete"}, ttl_seconds=0.01)
        time.sleep(0.05)
        assert gate.consume(approval.token, "dangerous", {"action": "delete"}) is False

    def test_revoked_rejected(self) -> None:
        gate = ConfirmationGate()
        approval = gate.grant("dangerous", {"action": "delete"})
        assert gate.revoke(approval.token) is True
        assert gate.consume(approval.token, "dangerous", {"action": "delete"}) is False

    def test_revoke_unknown_returns_false(self) -> None:
        assert ConfirmationGate().revoke("no-such-token") is False

    def test_consume_matching(self) -> None:
        gate = ConfirmationGate()
        gate.grant("dangerous", {"action": "delete"})
        assert gate.consume_matching("dangerous", {"action": "delete"}) is True
        assert gate.consume_matching("dangerous", {"action": "delete"}) is False

    def test_consume_matching_requires_exact_args(self) -> None:
        gate = ConfirmationGate()
        gate.grant("dangerous", {"action": "delete"})
        assert gate.consume_matching("dangerous", {"action": "other"}) is False
        assert gate.consume_matching("dangerous", {"action": "delete"}) is True

    def test_unknown_token_rejected(self) -> None:
        assert ConfirmationGate().consume("nope", "dangerous", {}) is False

    def test_canonical_arguments_order_insensitive(self) -> None:
        assert canonical_arguments({"b": 1, "a": 2}) == canonical_arguments(
            {"a": 2, "b": 1}
        )

    def test_grant_rejects_bad_input(self) -> None:
        gate = ConfirmationGate()
        with pytest.raises(ValueError):
            gate.grant("", {"a": 1})
        with pytest.raises(ValueError):
            gate.grant("dangerous", {"a": 1}, ttl_seconds=0)


# ---------------------------------------------------------------------------
# ToolExecutor confirmation enforcement
# ---------------------------------------------------------------------------


class TestExecutorConfirmation:
    def test_token_flow_executes_once(self) -> None:
        gate = ConfirmationGate()
        executor = ToolExecutor([_DangerousTool()], confirmation_gate=gate)
        approval = gate.grant("dangerous", {"action": "delete"})
        call = ToolCall(
            id="1",
            name="dangerous",
            arguments='{"action": "delete"}',
            approval_token=approval.token,
        )
        assert executor.execute(call).success is True
        # Replay the same token: rejected.
        assert executor.execute(call).success is False

    def test_token_with_tampered_args_rejected(self) -> None:
        gate = ConfirmationGate()
        executor = ToolExecutor([_DangerousTool()], confirmation_gate=gate)
        approval = gate.grant("dangerous", {"action": "delete"})
        call = ToolCall(
            id="1",
            name="dangerous",
            arguments='{"action": "delete-everything"}',
            approval_token=approval.token,
        )
        result = executor.execute(call)
        assert result.success is False
        assert "rejected" in result.content

    def test_token_flow_needs_no_interactive(self) -> None:
        gate = ConfirmationGate()
        executor = ToolExecutor(
            [_DangerousTool()], interactive=False, confirmation_gate=gate
        )
        approval = gate.grant("dangerous", {})
        call = ToolCall(
            id="1", name="dangerous", arguments="{}", approval_token=approval.token
        )
        assert executor.execute(call).success is True

    def test_pregranted_matching_approval_consumed(self) -> None:
        gate = ConfirmationGate()
        gate.grant("dangerous", {"action": "delete"})
        executor = ToolExecutor([_DangerousTool()], confirmation_gate=gate)
        call = ToolCall(id="1", name="dangerous", arguments='{"action": "delete"}')
        assert executor.execute(call).success is True
        assert executor.execute(call).success is False  # consumed

    def test_no_approval_fails_closed(self) -> None:
        executor = ToolExecutor([_DangerousTool()])
        call = ToolCall(id="1", name="dangerous", arguments="{}")
        result = executor.execute(call)
        assert result.success is False
        assert "requires confirmation" in result.content

    def test_prompt_approval_is_single_use(self) -> None:
        prompts: list[str] = []
        executor = ToolExecutor(
            [_DangerousTool()],
            interactive=True,
            confirm_callback=lambda p: prompts.append(p) or True,
        )
        call = ToolCall(id="1", name="dangerous", arguments='{"action": "delete"}')
        assert executor.execute(call).success is True
        # A second identical call must prompt again — the first approval
        # cannot be replayed.
        assert executor.execute(call).success is True
        assert len(prompts) == 2

    def test_expired_token_rejected_by_executor(self) -> None:
        gate = ConfirmationGate()
        executor = ToolExecutor([_DangerousTool()], confirmation_gate=gate)
        approval = gate.grant("dangerous", {}, ttl_seconds=0.01)
        time.sleep(0.05)
        call = ToolCall(
            id="1", name="dangerous", arguments="{}", approval_token=approval.token
        )
        assert executor.execute(call).success is False

    def test_safe_tool_unaffected(self) -> None:
        executor = ToolExecutor([_SafeTool()])
        call = ToolCall(id="1", name="safe", arguments="{}")
        assert executor.execute(call).success is True


# ---------------------------------------------------------------------------
# Canonical paths / symlink escapes
# ---------------------------------------------------------------------------


class TestCanonicalPaths:
    def test_symlink_escape_rejected(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret-data", encoding="utf-8")
        link = allowed / "escape.txt"
        link.symlink_to(outside)
        assert is_within(link, [allowed]) is False
        with pytest.raises(ValueError):
            resolve_within(link, [allowed])

    def test_dotdot_escape_rejected(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        assert is_within(allowed / ".." / "outside.txt", [allowed]) is False

    def test_in_root_symlink_allowed(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        target = allowed / "real.txt"
        target.write_text("ok", encoding="utf-8")
        link = allowed / "alias.txt"
        link.symlink_to(target)
        assert resolve_within(link, [allowed]) == target

    def test_parent_dir_symlink_escape_rejected(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "f.txt").write_text("x", encoding="utf-8")
        link_dir = tmp_path / "linkdir"
        link_dir.symlink_to(outside_dir, target_is_directory=True)
        assert is_within(link_dir / "f.txt", [allowed]) is False

    def test_file_read_blocks_symlink_escape(self, tmp_path: Path) -> None:
        from openjarvis.tools.file_read import FileReadTool

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("top-secret-content", encoding="utf-8")
        link = allowed / "escape.txt"
        link.symlink_to(outside)
        tool = FileReadTool(allowed_dirs=[str(allowed)])
        result = tool.execute(path=str(link))
        assert result.success is False
        assert "top-secret-content" not in result.content

    def test_file_write_blocks_symlink_escape(self, tmp_path: Path) -> None:
        from openjarvis.tools.file_write import FileWriteTool

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("original", encoding="utf-8")
        link = allowed / "escape.txt"
        link.symlink_to(outside)
        tool = FileWriteTool(allowed_dirs=[str(allowed)])
        result = tool.execute(path=str(link), content="pwned", mode="write")
        assert result.success is False
        assert outside.read_text(encoding="utf-8") == "original"

    def test_apply_patch_blocks_symlink_escape(self, tmp_path: Path) -> None:
        from openjarvis.tools.apply_patch import ApplyPatchTool

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("line1\nline2\nline3\n", encoding="utf-8")
        link = allowed / "escape.txt"
        link.symlink_to(outside)
        patch = (
            "--- a/escape.txt\n"
            "+++ b/escape.txt\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+pwned\n"
            " line3\n"
        )
        tool = ApplyPatchTool(allowed_dirs=[str(allowed)])
        result = tool.execute(patch=patch, path=str(link), backup=False)
        assert result.success is False
        assert "pwned" not in outside.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Shell disabled by default
# ---------------------------------------------------------------------------


class TestShellOptIn:
    def test_shell_disabled_without_opt_in(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from openjarvis.tools.shell_exec import ShellExecTool

        monkeypatch.delenv("OPENJARVIS_SHELL_ENABLED", raising=False)
        result = ShellExecTool().execute(command="echo hi")
        assert result.success is False
        assert "disabled" in result.content.lower()

    def test_shell_opt_in_requires_confirmation_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from openjarvis.tools.shell_exec import ShellExecTool

        monkeypatch.setenv("OPENJARVIS_SHELL_ENABLED", "1")
        # Opt-in alone is not approval: executor without approval fails closed.
        executor = ToolExecutor([ShellExecTool()])
        call = ToolCall(id="1", name="shell_exec", arguments='{"command": "echo hi"}')
        result = executor.execute(call)
        assert result.success is False
        assert "confirmation" in result.content.lower()

    def test_shell_opt_in_plus_approval_executes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from openjarvis.tools.shell_exec import ShellExecTool

        monkeypatch.setenv("OPENJARVIS_SHELL_ENABLED", "1")
        gate = ConfirmationGate()
        executor = ToolExecutor([ShellExecTool()], confirmation_gate=gate)
        approval = gate.grant("shell_exec", {"command": "echo hi"})
        call = ToolCall(
            id="1",
            name="shell_exec",
            arguments='{"command": "echo hi"}',
            approval_token=approval.token,
        )
        result = executor.execute(call)
        assert result.success is True
        assert "hi" in result.content

    def test_shell_spec_requires_confirmation(self) -> None:
        from openjarvis.tools.shell_exec import ShellExecTool

        assert ShellExecTool().spec.requires_confirmation is True

    def test_docker_shell_requires_confirmation(self) -> None:
        from openjarvis.tools.docker_shell_exec import DockerShellExecTool

        assert DockerShellExecTool().spec.requires_confirmation is True


# ---------------------------------------------------------------------------
# Keychain
# ---------------------------------------------------------------------------


class _MemoryKeychainBackend:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str):
        return self.store.get((service, account))

    def set_password(self, service: str, account: str, password: str) -> None:
        self.store[(service, account)] = password

    def delete_password(self, service: str, account: str) -> None:
        self.store.pop((service, account), None)


class TestKeychain:
    def test_memory_backend_roundtrip(self) -> None:
        keychain = Keychain(backend=_MemoryKeychainBackend())
        assert keychain.get("vault-key") is None
        keychain.set("vault-key", "k1")
        assert keychain.get("vault-key") == "k1"
        keychain.delete("vault-key")
        assert keychain.get("vault-key") is None

    def test_no_backend_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import openjarvis.security.keychain as keychain_mod

        monkeypatch.setattr(keychain_mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(keychain_mod.shutil, "which", lambda _: None)
        with pytest.raises(KeychainUnavailable):
            get_default_backend()

    def test_keychain_unavailable_propagates(self) -> None:
        class _Broken:
            def get_password(self, service, account):
                raise KeychainUnavailable("no daemon")

            def set_password(self, service, account, password):
                raise KeychainUnavailable("no daemon")

            def delete_password(self, service, account):
                raise KeychainUnavailable("no daemon")

        keychain = Keychain(backend=_Broken())
        with pytest.raises(KeychainUnavailable):
            keychain.get("vault-key")


# ---------------------------------------------------------------------------
# Streaming output scanned BEFORE delivery
# ---------------------------------------------------------------------------


class TestStreamingPreDeliveryScan:
    def test_redact_mode_never_delivers_split_secret(self) -> None:
        marker = _FakeSecretScanner.MARKER
        # Split the secret across chunk boundaries: no single chunk
        # contains the whole marker.
        tokens = ["key: ", marker[:8], marker[8:16], marker[16:], " done"]
        engine = GuardrailsEngine(
            _FakeEngine(tokens),
            scanners=[_FakeSecretScanner()],
            mode=RedactionMode.REDACT,
        )
        delivered = "".join(
            asyncio.run(_collect(engine.stream([Message(Role.USER, "hi")], model="t")))
        )
        assert marker not in delivered
        assert "[REDACTED:fake_secret]" in delivered

    def test_block_mode_raises_before_secret_delivery(self) -> None:
        marker = _FakeSecretScanner.MARKER
        tokens = ["prefix ", marker, " suffix"]
        engine = GuardrailsEngine(
            _FakeEngine(tokens),
            scanners=[_FakeSecretScanner()],
            mode=RedactionMode.BLOCK,
        )

        async def _run():
            seen = []
            try:
                async for chunk in engine.stream([Message(Role.USER, "hi")], model="t"):
                    seen.append(chunk)
            except SecurityBlockError:
                return seen
            raise AssertionError("BLOCK mode did not raise")

        seen = asyncio.run(_run())
        assert marker not in "".join(seen)

    def test_stream_full_scans_before_delivery(self) -> None:
        marker = _FakeSecretScanner.MARKER
        tokens = ["key: ", marker, " done"]
        engine = GuardrailsEngine(
            _FakeEngine(tokens),
            scanners=[_FakeSecretScanner()],
            mode=RedactionMode.REDACT,
        )

        async def _run():
            chunks = []
            async for chunk in engine.stream_full(
                [Message(Role.USER, "hi")], model="t"
            ):
                chunks.append(chunk.content or "")
            return "".join(chunks)

        delivered = asyncio.run(_run())
        assert marker not in delivered
        assert "[REDACTED:fake_secret]" in delivered


async def _collect(agen):
    out = []
    async for item in agen:
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Server tool-approval endpoints share the gate with the executor
# ---------------------------------------------------------------------------


class TestServerToolApprovals:
    def test_grant_revoke_and_consume_via_http(self) -> None:
        pytest.importorskip("fastapi")
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from openjarvis.server.approval_routes import router

        gate = ConfirmationGate()
        app = FastAPI()
        app.state.confirmation_gate = gate
        app.include_router(router)
        client = TestClient(app)

        grant = client.post(
            "/v1/approvals/tool",
            json={"tool_name": "dangerous", "arguments": {"action": "delete"}},
        )
        assert grant.status_code == 200
        assert grant.json()["token"]

        executor = ToolExecutor([_DangerousTool()], confirmation_gate=gate)
        call = ToolCall(id="1", name="dangerous", arguments='{"action": "delete"}')
        assert executor.execute(call).success is True  # consumed by match
        assert executor.execute(call).success is False  # single use

        # Revoke path: grant again, revoke, then the grant is dead.
        grant2 = client.post(
            "/v1/approvals/tool",
            json={"tool_name": "dangerous", "arguments": {"action": "delete"}},
        )
        assert grant2.status_code == 200
        revoke = client.post(
            "/v1/approvals/tool/revoke", json={"token": grant2.json()["token"]}
        )
        assert revoke.status_code == 200
        assert executor.execute(call).success is False

    def test_grant_validation(self) -> None:
        pytest.importorskip("fastapi")
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from openjarvis.server.approval_routes import router

        app = FastAPI()
        app.state.confirmation_gate = ConfirmationGate()
        app.include_router(router)
        client = TestClient(app)
        assert (
            client.post("/v1/approvals/tool", json={"tool_name": ""}).status_code == 422
        )
        assert (
            client.post(
                "/v1/approvals/tool",
                json={"tool_name": "dangerous", "arguments": "not-a-dict"},
            ).status_code
            == 422
        )
        assert (
            client.post("/v1/approvals/tool/revoke", json={"token": "nope"}).status_code
            == 404
        )


# ---------------------------------------------------------------------------
# Vault: no keychain, no vault (covered in tests/cli/test_vault_cmd.py too)
# ---------------------------------------------------------------------------


class TestVaultKeychainOnly:
    def test_vault_key_never_written_to_file(self, tmp_path: Path, monkeypatch) -> None:
        pytest.importorskip("cryptography")
        import openjarvis.cli.vault_cmd as vault_cmd

        store: dict = {}

        class _FakeKeychain:
            def get(self, account):
                return store.get(account)

            def set(self, account, value):
                store[account] = value

            def delete(self, account):
                store.pop(account, None)

        monkeypatch.setattr(vault_cmd, "_VAULT_FILE", tmp_path / "vault.enc")
        monkeypatch.setattr(vault_cmd, "_LEGACY_KEY_FILE", tmp_path / ".vault_key")
        monkeypatch.setattr(vault_cmd, "DEFAULT_CONFIG_DIR", tmp_path)
        monkeypatch.setattr(vault_cmd, "Keychain", lambda: _FakeKeychain())
        vault_cmd._save_vault({"K": "v"})
        assert (tmp_path / "vault.enc").exists()
        assert not (tmp_path / ".vault_key").exists()
        assert vault_cmd._load_vault() == {"K": "v"}
