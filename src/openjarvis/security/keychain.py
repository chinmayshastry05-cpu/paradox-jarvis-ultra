"""OS keychain access for secret storage (e.g. the vault encryption key).

Backends use only the standard library and the platform's own
credential store:

- macOS: ``security`` CLI (Keychain)
- Windows: Credential Vault via ``ctypes`` (``CredReadW``/``CredWriteW``)
- Linux: Secret Service via the ``secret-tool`` CLI (libsecret)

There is deliberately NO file/plaintext fallback. If no backend is
available — no keychain daemon, no ``secret-tool``, headless session —
every operation raises :class:`KeychainUnavailable` and the caller must
fail closed. Callers must never catch that and fall back to a file.

Secrets are never logged: only service/account names appear in errors.
"""

from __future__ import annotations

import ctypes
import platform
import shutil
import subprocess
from typing import Optional, Protocol


class KeychainError(Exception):
    """Keychain operation failed."""


class KeychainUnavailable(KeychainError):
    """No usable OS keychain backend on this machine/session."""


class KeychainBackend(Protocol):
    """A single OS credential store."""

    def get_password(self, service: str, account: str) -> Optional[str]:
        """Return the stored password, or None if no such item exists."""

    def set_password(self, service: str, account: str, password: str) -> None:
        """Create or update the stored password."""

    def delete_password(self, service: str, account: str) -> None:
        """Delete the stored password; no-op if it does not exist."""


def _run(
    argv: list[str], *, input_text: Optional[str] = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


class MacOSKeychainBackend:
    """macOS Keychain via the ``security`` CLI."""

    def get_password(self, service: str, account: str) -> Optional[str]:
        try:
            result = _run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    service,
                    "-a",
                    account,
                    "-w",
                ]
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KeychainUnavailable(f"macOS keychain unavailable: {exc}") from exc
        if result.returncode == 0:
            return result.stdout.rstrip("\n")
        if result.returncode == 44:  # errSecItemNotFound
            return None
        raise KeychainError(
            f"macOS keychain lookup failed for service={service!r} "
            f"(exit {result.returncode})"
        )

    def set_password(self, service: str, account: str, password: str) -> None:
        try:
            result = _run(
                [
                    "security",
                    "add-generic-password",
                    "-s",
                    service,
                    "-a",
                    account,
                    "-w",
                    password,
                    "-U",  # update if the item already exists
                ]
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KeychainUnavailable(f"macOS keychain unavailable: {exc}") from exc
        if result.returncode != 0:
            raise KeychainError(
                f"macOS keychain store failed for service={service!r} "
                f"(exit {result.returncode})"
            )

    def delete_password(self, service: str, account: str) -> None:
        try:
            result = _run(
                ["security", "delete-generic-password", "-s", service, "-a", account]
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KeychainUnavailable(f"macOS keychain unavailable: {exc}") from exc
        if result.returncode not in (0, 44):  # 44 = already absent
            raise KeychainError(
                f"macOS keychain delete failed for service={service!r} "
                f"(exit {result.returncode})"
            )


class SecretToolBackend:
    """Linux Secret Service via the ``secret-tool`` CLI (libsecret)."""

    def __init__(self) -> None:
        if shutil.which("secret-tool") is None:
            raise KeychainUnavailable(
                "secret-tool not found: no Secret Service keychain available"
            )

    def get_password(self, service: str, account: str) -> Optional[str]:
        try:
            result = _run(
                ["secret-tool", "lookup", "service", service, "account", account]
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KeychainUnavailable(f"Secret Service unavailable: {exc}") from exc
        if result.returncode == 0:
            return result.stdout.rstrip("\n") or None
        if result.returncode == 1 and not result.stdout.strip():
            return None  # not found
        raise KeychainError(
            f"Secret Service lookup failed for service={service!r} "
            f"(exit {result.returncode})"
        )

    def set_password(self, service: str, account: str, password: str) -> None:
        try:
            result = _run(
                [
                    "secret-tool",
                    "store",
                    "--label",
                    f"OpenJarvis {service}",
                    "service",
                    service,
                    "account",
                    account,
                ],
                input_text=password,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KeychainUnavailable(f"Secret Service unavailable: {exc}") from exc
        if result.returncode != 0:
            raise KeychainError(
                f"Secret Service store failed for service={service!r} "
                f"(exit {result.returncode})"
            )

    def delete_password(self, service: str, account: str) -> None:
        try:
            result = _run(
                ["secret-tool", "clear", "service", service, "account", account]
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KeychainUnavailable(f"Secret Service unavailable: {exc}") from exc
        if result.returncode != 0:
            raise KeychainError(
                f"Secret Service delete failed for service={service!r} "
                f"(exit {result.returncode})"
            )


class WindowsCredentialBackend:
    """Windows Credential Vault via ``ctypes`` (no third-party dependency)."""

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise KeychainUnavailable("Windows Credential Vault is Windows-only")
        try:
            self._advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        except (AttributeError, OSError) as exc:
            raise KeychainUnavailable("Windows Credential Vault unavailable") from exc

    def _target(self, service: str, account: str) -> str:
        return f"{service}:{account}"

    def get_password(self, service: str, account: str) -> Optional[str]:
        class _Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", ctypes.c_ulong),
                ("Type", ctypes.c_ulong),
                ("TargetName", ctypes.c_wchar_p),
                ("Comment", ctypes.c_wchar_p),
                ("LastWritten", ctypes.c_ulonglong),
                ("CredentialBlobSize", ctypes.c_ulong),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", ctypes.c_ulong),
                ("AttributeCount", ctypes.c_ulong),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.c_wchar_p),
                ("UserName", ctypes.c_wchar_p),
            ]

        cred_ptr = ctypes.POINTER(_Credential)()
        ok = self._advapi32.CredReadW(
            self._target(service, account), 1, 0, ctypes.byref(cred_ptr)
        )
        if not ok:
            err = ctypes.get_last_error()
            if err == 1168:  # ERROR_NOT_FOUND
                return None
            raise KeychainError(
                f"Windows Credential Vault lookup failed for service={service!r} "
                f"(error {err})"
            )
        try:
            cred = cred_ptr.contents
            blob = bytes(
                ctypes.cast(
                    cred.CredentialBlob,
                    ctypes.POINTER(ctypes.c_byte * cred.CredentialBlobSize),
                ).contents
            )
            return blob.decode("utf-16-le")
        finally:
            self._advapi32.CredFree(ctypes.byref(cred_ptr))

    def set_password(self, service: str, account: str, password: str) -> None:
        blob = password.encode("utf-16-le")

        class _Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", ctypes.c_ulong),
                ("Type", ctypes.c_ulong),
                ("TargetName", ctypes.c_wchar_p),
                ("Comment", ctypes.c_wchar_p),
                ("LastWritten", ctypes.c_ulonglong),
                ("CredentialBlobSize", ctypes.c_ulong),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", ctypes.c_ulong),
                ("AttributeCount", ctypes.c_ulong),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.c_wchar_p),
                ("UserName", ctypes.c_wchar_p),
            ]

        cred = _Credential()
        cred.Flags = 0
        cred.Type = 1  # CRED_TYPE_GENERIC
        cred.TargetName = self._target(service, account)
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(
            ctypes.create_string_buffer(blob, len(blob)), ctypes.POINTER(ctypes.c_byte)
        )
        cred.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = account
        ok = self._advapi32.CredWriteW(ctypes.byref(cred), 0)
        if not ok:
            err = ctypes.get_last_error()
            raise KeychainError(
                f"Windows Credential Vault store failed for service={service!r} "
                f"(error {err})"
            )

    def delete_password(self, service: str, account: str) -> None:
        ok = self._advapi32.CredDeleteW(self._target(service, account), 1, 0)
        if not ok:
            err = ctypes.get_last_error()
            if err == 1168:  # ERROR_NOT_FOUND
                return
            raise KeychainError(
                f"Windows Credential Vault delete failed for service={service!r} "
                f"(error {err})"
            )


def get_default_backend() -> KeychainBackend:
    """Return the platform keychain backend, or raise KeychainUnavailable."""
    system = platform.system()
    if system == "Darwin":
        return MacOSKeychainBackend()
    if system == "Windows":
        return WindowsCredentialBackend()
    if system == "Linux":
        return SecretToolBackend()
    raise KeychainUnavailable(f"no keychain backend for platform {system!r}")


class Keychain:
    """Thin wrapper over a :class:`KeychainBackend` for one service."""

    def __init__(
        self,
        backend: Optional[KeychainBackend] = None,
        *,
        service: str = "openjarvis-vault",
    ) -> None:
        self._backend = backend if backend is not None else get_default_backend()
        self._service = service

    @property
    def service(self) -> str:
        return self._service

    def get(self, account: str) -> Optional[str]:
        return self._backend.get_password(self._service, account)

    def set(self, account: str, password: str) -> None:
        self._backend.set_password(self._service, account, password)

    def delete(self, account: str) -> None:
        self._backend.delete_password(self._service, account)

    def is_available(self) -> bool:
        """True if the backend answers (even with "item not found")."""
        try:
            self._backend.get_password(self._service, "__openjarvis_probe__")
            return True
        except KeychainUnavailable:
            return False
        except KeychainError:
            # Backend answered but the probe itself failed — still present.
            return True


__all__ = [
    "Keychain",
    "KeychainBackend",
    "KeychainError",
    "KeychainUnavailable",
    "MacOSKeychainBackend",
    "SecretToolBackend",
    "WindowsCredentialBackend",
    "get_default_backend",
]
