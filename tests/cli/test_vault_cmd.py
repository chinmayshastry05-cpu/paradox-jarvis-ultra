"""Tests for the ``jarvis vault`` CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from openjarvis.cli.vault_cmd import vault


class TestVaultCmd:
    def test_vault_group_help(self) -> None:
        result = CliRunner().invoke(vault, ["--help"])
        assert result.exit_code == 0
        assert "set" in result.output
        assert "get" in result.output
        assert "list" in result.output
        assert "remove" in result.output

    def test_vault_set_help(self) -> None:
        result = CliRunner().invoke(vault, ["set", "--help"])
        assert result.exit_code == 0

    def test_vault_get_help(self) -> None:
        result = CliRunner().invoke(vault, ["get", "--help"])
        assert result.exit_code == 0

    def test_vault_list_empty(self) -> None:
        with mock.patch(
            "openjarvis.cli.vault_cmd._VAULT_FILE",
            Path("/nonexistent/vault.enc"),
        ):
            result = CliRunner().invoke(vault, ["list"])
            assert result.exit_code == 0
            assert "empty" in result.output.lower()

    def test_vault_roundtrip(self, tmp_path: Path) -> None:
        pytest.importorskip("cryptography")

        vault_file = tmp_path / "vault.enc"
        store: dict = {}

        class _FakeKeychain:
            def get(self, account: str):
                return store.get(account)

            def set(self, account: str, value: str) -> None:
                store[account] = value

            def delete(self, account: str) -> None:
                store.pop(account, None)

        with (
            mock.patch("openjarvis.cli.vault_cmd._VAULT_FILE", vault_file),
            mock.patch(
                "openjarvis.cli.vault_cmd._LEGACY_KEY_FILE",
                tmp_path / ".vault_key",
            ),
            mock.patch(
                "openjarvis.cli.vault_cmd.DEFAULT_CONFIG_DIR",
                tmp_path,
            ),
            mock.patch(
                "openjarvis.cli.vault_cmd.Keychain",
                return_value=_FakeKeychain(),
            ),
        ):
            runner = CliRunner()

            # Set a credential
            result = runner.invoke(vault, ["set", "MY_API_KEY", "secret123"])
            assert result.exit_code == 0

            # Get it back
            result = runner.invoke(vault, ["get", "MY_API_KEY"])
            assert result.exit_code == 0
            assert "secret123" in result.output

            # The key lives in the keychain (the fake store), never in a
            # file next to the ciphertext.
            assert vault_file.exists()
            assert not (tmp_path / ".vault_key").exists()
            assert store, "key should have been stored in the keychain"

    def test_vault_set_fails_closed_without_keychain(self, tmp_path: Path) -> None:
        """Keychain unavailable → set fails, nothing is written anywhere."""
        from openjarvis.security.keychain import KeychainUnavailable

        vault_file = tmp_path / "vault.enc"
        with (
            mock.patch("openjarvis.cli.vault_cmd._VAULT_FILE", vault_file),
            mock.patch(
                "openjarvis.cli.vault_cmd._LEGACY_KEY_FILE",
                tmp_path / ".vault_key",
            ),
            mock.patch(
                "openjarvis.cli.vault_cmd.DEFAULT_CONFIG_DIR",
                tmp_path,
            ),
            mock.patch(
                "openjarvis.cli.vault_cmd.Keychain",
                side_effect=KeychainUnavailable("no backend"),
            ),
        ):
            result = CliRunner().invoke(vault, ["set", "K", "v"])
            assert result.exit_code == 1
            assert not vault_file.exists()
            assert not (tmp_path / ".vault_key").exists()

    def test_vault_remove_not_found(self) -> None:
        with mock.patch(
            "openjarvis.cli.vault_cmd._VAULT_FILE",
            Path("/nonexistent/vault.enc"),
        ):
            result = CliRunner().invoke(vault, ["remove", "nonexistent"])
            assert result.exit_code == 0
            assert "not found" in result.output.lower()
