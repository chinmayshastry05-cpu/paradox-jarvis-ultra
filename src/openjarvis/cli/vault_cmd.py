"""``jarvis vault`` — encrypted credential store.

The vault ciphertext lives at ``~/.openjarvis/vault.enc``. Its Fernet
key lives ONLY in the OS keychain (see
``openjarvis.security.keychain``) — never in a file next to the
ciphertext, never in plaintext anywhere. If no keychain backend is
available, every vault command fails closed: no key is created, no
plaintext fallback is used, and existing ciphertext cannot be opened.

One-time migration: if the keychain holds no key but the legacy
plaintext key file (``~/.openjarvis/.vault_key``, written by older
versions) still exists, its key is imported into the keychain and the
legacy file is securely deleted (overwritten, then unlinked). This runs
only when a working keychain backend is available.
"""

from __future__ import annotations

import base64
import binascii
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from openjarvis.core.config import DEFAULT_CONFIG_DIR
from openjarvis.security.keychain import Keychain, KeychainError

_VAULT_FILE = DEFAULT_CONFIG_DIR / "vault.enc"
_LEGACY_KEY_FILE = DEFAULT_CONFIG_DIR / ".vault_key"
_VAULT_KEY_ACCOUNT = "vault-key"


def _secure_delete(path: Path) -> None:
    """Overwrite a file with zeros, then unlink it. Best effort."""
    try:
        size = path.stat().st_size
        with open(path, "r+b") as handle:
            handle.write(b"\x00" * size)
            handle.flush()
    except OSError:
        pass
    try:
        path.unlink()
    except OSError:
        pass


def _is_fernet_key(raw: bytes) -> bool:
    """True iff *raw* decodes as a 32-byte Fernet key."""
    try:
        decoded = base64.urlsafe_b64decode(raw.strip())
    except (binascii.Error, ValueError):
        return False
    return len(decoded) == 32


def _get_or_create_key(
    keychain: Keychain | None = None, *, create: bool = True
) -> bytes | None:
    """Get the vault key from the OS keychain, or create and store one.

    With ``create=False`` returns None instead of minting a key, so
    loading an existing vault never silently rotates its key away.
    Raises :class:`KeychainError` when no keychain backend is available
    or the keychain operation fails. Never falls back to a file.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise ImportError(
            "cryptography not installed. Install with: uv sync --extra security-signing"
        )

    keychain = keychain or Keychain()
    stored = keychain.get(_VAULT_KEY_ACCOUNT)
    if stored is not None:
        raw = stored.strip().encode("ascii")
        if not _is_fernet_key(raw):
            raise KeychainError(
                "vault key in the OS keychain is not a valid Fernet key"
            )
        return raw

    # No key in the keychain: one-time migration from the legacy file.
    # Only runs because the keychain backend above answered; the legacy
    # file is never used as an ongoing fallback.
    if _LEGACY_KEY_FILE.exists():
        raw = _LEGACY_KEY_FILE.read_bytes().strip()
        if _is_fernet_key(raw):
            keychain.set(_VAULT_KEY_ACCOUNT, raw.decode("ascii"))
            _secure_delete(_LEGACY_KEY_FILE)
            return raw
        raise KeychainError(
            f"legacy vault key file {_LEGACY_KEY_FILE} is not a valid Fernet key; "
            "remove it or restore a valid key to continue"
        )

    if not create:
        return None
    key = Fernet.generate_key()
    keychain.set(_VAULT_KEY_ACCOUNT, key.decode("ascii"))
    return key


def _load_vault(keychain: Keychain | None = None) -> dict:
    """Load and decrypt vault contents. Empty dict iff no vault file yet.

    Raises :class:`KeychainError` when the keychain is unavailable and
    :class:`ValueError` when the ciphertext cannot be decrypted (wrong
    key / corrupt file) — never silently returns an empty vault for a
    file that exists but cannot be opened.
    """
    if not _VAULT_FILE.exists():
        return {}
    try:
        from cryptography.fernet import Fernet

        key = _get_or_create_key(keychain, create=False)
        if key is None:
            raise ValueError(
                "vault exists but no vault key is in the OS keychain; "
                "restore the key to the keychain before opening it"
            )
        f = Fernet(key)
        encrypted = _VAULT_FILE.read_bytes()
        decrypted = f.decrypt(encrypted)
        return json.loads(decrypted.decode())
    except KeychainError:
        raise
    except Exception as exc:
        raise ValueError(f"cannot decrypt vault {_VAULT_FILE}: {exc}") from exc


def _save_vault(data: dict, keychain: Keychain | None = None) -> None:
    """Encrypt and save vault contents."""
    from cryptography.fernet import Fernet

    key = _get_or_create_key(keychain)
    if key is None:  # unreachable with create=True; defensive
        raise KeychainError("could not obtain a vault key from the OS keychain")
    f = Fernet(key)
    plaintext = json.dumps(data).encode()
    encrypted = f.encrypt(plaintext)
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _VAULT_FILE.write_bytes(encrypted)
    _VAULT_FILE.chmod(0o600)


@click.group()
def vault() -> None:
    """Manage encrypted credentials."""


@vault.command("set")
@click.argument("key")
@click.argument("value")
def vault_set(key: str, value: str) -> None:
    """Store a credential in the vault."""
    console = Console(stderr=True)
    try:
        data = _load_vault()
        data[key] = value
        _save_vault(data)
        console.print(f"[green]Stored credential: {key}[/green]")
    except (ImportError, KeychainError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


@vault.command("get")
@click.argument("key")
def vault_get(key: str) -> None:
    """Retrieve a credential from the vault."""
    console = Console(stderr=True)
    try:
        data = _load_vault()
        if key in data:
            console.print(data[key])
        else:
            console.print(f"[yellow]Key not found: {key}[/yellow]")
    except (ImportError, KeychainError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


@vault.command("list")
def vault_list() -> None:
    """List all stored credential keys."""
    console = Console(stderr=True)
    try:
        data = _load_vault()
        if not data:
            console.print("[dim]Vault is empty.[/dim]")
            return
        table = Table(title="Vault Keys")
        table.add_column("Key", style="cyan")
        table.add_column("Value Preview", style="dim")
        for k, v in sorted(data.items()):
            preview = v[:4] + "****" if len(v) > 4 else "****"
            table.add_row(k, preview)
        console.print(table)
    except (ImportError, KeychainError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


@vault.command("remove")
@click.argument("key")
def vault_remove(key: str) -> None:
    """Remove a credential from the vault."""
    console = Console(stderr=True)
    try:
        data = _load_vault()
        if key in data:
            del data[key]
            _save_vault(data)
            console.print(f"[green]Removed: {key}[/green]")
        else:
            console.print(f"[yellow]Key not found: {key}[/yellow]")
    except (ImportError, KeychainError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


__all__ = ["vault"]
