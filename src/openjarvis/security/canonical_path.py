"""Canonical path / symlink checks for file tool paths.

Every filesystem tool must resolve symlinks (including symlinks in
parent directories) *before* deciding whether a path is allowed, and
reject any path whose resolved form escapes the configured allowed
roots. Checking the unresolved user-supplied string is not enough: a
symlink inside an allowed root can point anywhere on the filesystem.

TOCTOU: :func:`resolve_within` / :func:`is_within` are string-level
pre-checks only — they must NOT be used to authorise an open, because a
path can be swapped for a symlink between the check and the open.
Filesystem tools must open through :func:`open_within` (and its
``read_bytes_within`` / ``open_for_write_within`` /
``open_rdwr_within`` wrappers), which walks the path component by
component holding a file descriptor for each directory, resolves
symlinks via ``os.readlink(..., dir_fd=...)`` on those descriptors, and
opens the final component with ``os.open(..., dir_fd=...)`` +
``O_NOFOLLOW`` anchored on the parent descriptor. The path
string is never re-opened after the walk, so a
racing swap of any component cannot redirect the open: a swapped final
symlink fails with ``O_NOFOLLOW``, and a swapped regular file fails the
dev/ino identity check. Creation uses ``O_CREAT | O_EXCL`` so a
symlink/file appearing between the walk and the create is refused
rather than followed or truncated.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

PathLike = Union[str, os.PathLike]


class UnsupportedPlatformError(RuntimeError):
    """Descriptor-based containment is unavailable on this platform."""


class UnsafePathError(ValueError):
    """Path is outside the allowed roots or was swapped during open."""


def resolve_allowed_roots(allowed_roots: Optional[Iterable[PathLike]]) -> List[Path]:
    """Resolve every allowed root. An empty list means "no boundary"."""
    if not allowed_roots:
        return []
    roots: List[Path] = []
    for root in allowed_roots:
        roots.append(Path(os.fspath(root)).expanduser().resolve())
    return roots


def resolve_within(
    path: PathLike,
    allowed_roots: Optional[Iterable[PathLike]],
    *,
    base: Optional[PathLike] = None,
) -> Path:
    """Resolve *path* (symlinks included) and require containment.

    Relative paths are resolved against *base* when given. Returns the
    fully resolved path.

    Raises :class:`ValueError` if the path cannot be resolved (symlink
    loop, unreadable component) or its resolved form is not equal to or
    under one of the resolved *allowed_roots*. An empty *allowed_roots*
    means no boundary is configured, so the resolved path is returned
    unchanged.

    .. warning:: This is a pre-check only. Do not open the returned path
        by string — use :func:`open_within`, which holds descriptors.
    """
    candidate = Path(os.fspath(path)).expanduser()
    if not candidate.is_absolute() and base is not None:
        candidate = Path(os.fspath(base)).expanduser() / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"cannot resolve path {str(path)!r}: {exc}") from exc
    roots = resolve_allowed_roots(allowed_roots)
    if not roots:
        return resolved
    for root in roots:
        if resolved == root or resolved.is_relative_to(root):
            return resolved
    raise UnsafePathError(
        f"path {str(path)!r} resolves to {resolved} which is outside "
        f"the allowed roots: {[str(r) for r in roots]}"
    )


def is_within(
    path: PathLike,
    allowed_roots: Optional[Iterable[PathLike]],
    *,
    base: Optional[PathLike] = None,
) -> bool:
    """Return True iff :func:`resolve_within` would accept *path*."""
    try:
        resolve_within(path, allowed_roots, base=base)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Descriptor-based open (TOCTOU-safe where the platform supports it)
# ---------------------------------------------------------------------------

_MAX_SYMLINK_HOPS = 40
_MAX_WALK_STEPS = 2000


def _dir_fd_supported() -> bool:
    supported = getattr(os, "supports_dir_fd", set())
    return (
        all(fn in supported for fn in (os.open, os.readlink, os.stat, os.mkdir))
        and hasattr(os, "O_NOFOLLOW")
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_CLOEXEC")
    )


def _require_descriptor_open() -> None:
    if not _dir_fd_supported():
        raise UnsupportedPlatformError(
            "descriptor-based containment needs os.open/readlink/stat/mkdir "
            "with dir_fd plus O_NOFOLLOW/O_DIRECTORY (POSIX); this "
            "platform lacks them"
        )


def _is_symlink_at(parent_fd: int, comp: str) -> bool:
    """True iff *comp* in *parent_fd* is a symlink (never follows it)."""
    try:
        return stat.S_ISLNK(
            os.stat(comp, dir_fd=parent_fd, follow_symlinks=False).st_mode
        )
    except OSError:
        return False


def _close_all(fds: Iterable[int]) -> None:
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass


def _fd_walk(
    path: PathLike,
    allowed_roots: Optional[Iterable[PathLike]],
    *,
    base: Optional[PathLike] = None,
) -> Tuple[int, str, Path, Optional[os.stat_result]]:
    """Walk *path* on descriptors; return (parent_fd, final_name, resolved, stat).

    The caller owns ``parent_fd`` and must close it after opening the
    final component. ``stat`` is the ``os.stat(..., follow_symlinks=False)``
    result for the final component, or ``None`` if it does not exist.
    Raises :class:`UnsafePathError` when the resolved path escapes the
    roots, :class:`UnsupportedPlatformError` on platforms without
    descriptor opens, and :class:`FileNotFoundError` / :class:`OSError`
    for missing / unreadable components.
    """
    _require_descriptor_open()
    candidate = Path(os.fspath(path)).expanduser()
    if not candidate.is_absolute() and base is not None:
        candidate = Path(os.fspath(base)).expanduser() / candidate
    if not candidate.is_absolute():
        candidate = Path(os.getcwd()) / candidate
    parts = [part for part in candidate.parts[1:] if part not in ("", "/")]
    if not parts:
        raise UnsafePathError(f"path {str(path)!r} has no final component")

    roots = resolve_allowed_roots(allowed_roots)
    root_fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    # fd_stack[i] is the descriptor for resolved_parts[:i]; stack[0] is "/".
    fd_stack: List[int] = [root_fd]
    resolved_parts: List[str] = []
    pending: List[str] = list(parts)
    hops = 0
    steps = 0
    try:
        while pending:
            steps += 1
            if steps > _MAX_WALK_STEPS:
                raise UnsafePathError(f"path {str(path)!r} exceeds walk step limit")
            comp = pending.pop(0)
            if comp in ("", "."):
                continue
            if comp == "..":
                if resolved_parts:
                    resolved_parts.pop()
                    _close_all([fd_stack.pop()])
                continue
            is_final = not pending
            parent_fd = fd_stack[-1]
            if is_final:
                try:
                    st = os.stat(comp, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    resolved = Path(os.sep + os.sep.join([*resolved_parts, comp]))
                    return _finish_walk(
                        fd_stack, parent_fd, comp, resolved, None, roots, path
                    )
                if stat.S_ISLNK(st.st_mode):
                    hops = _follow_symlink(
                        parent_fd,
                        comp,
                        pending,
                        fd_stack,
                        resolved_parts,
                        hops,
                        path,
                    )
                    continue
                resolved = Path(os.sep + os.sep.join([*resolved_parts, comp]))
                return _finish_walk(
                    fd_stack, parent_fd, comp, resolved, st, roots, path
                )
            # Intermediate component: open the directory, never following.
            try:
                child = os.open(
                    comp,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                # O_DIRECTORY|O_NOFOLLOW on a symlink yields ENOTDIR,
                # not ELOOP, on Linux: check explicitly.
                if exc.errno in (errno.ELOOP, errno.ENOTDIR) and _is_symlink_at(
                    parent_fd, comp
                ):
                    hops = _follow_symlink(
                        parent_fd,
                        comp,
                        pending,
                        fd_stack,
                        resolved_parts,
                        hops,
                        path,
                    )
                    continue
                raise
            fd_stack.append(child)
            resolved_parts.append(comp)
        # Unreachable: pending is non-empty on entry and only shrinks to
        # zero via the final-component branch, which always returns.
        raise UnsafePathError(f"path {str(path)!r} has no final component")
    except BaseException:
        _close_all(fd_stack)
        raise


def _finish_walk(fd_stack, parent_fd, comp, resolved, st, roots, path):
    """Check containment, then hand the parent fd to the caller."""
    if roots and not any(
        resolved == root or resolved.is_relative_to(root) for root in roots
    ):
        _close_all(fd_stack)
        raise UnsafePathError(
            f"path {str(path)!r} resolves to {resolved} which is outside "
            f"the allowed roots: {[str(r) for r in roots]}"
        )
    # Close every stacked fd except the parent, which the caller owns.
    for fd in fd_stack:
        if fd != parent_fd:
            try:
                os.close(fd)
            except OSError:
                pass
    return parent_fd, comp, resolved, st


def _follow_symlink(parent_fd, comp, pending, fd_stack, resolved_parts, hops, path):
    """Push a symlink's target components onto *pending* (bounded)."""
    hops += 1
    if hops > _MAX_SYMLINK_HOPS:
        raise UnsafePathError(f"path {str(path)!r} exceeds symlink hop limit (loop?)")
    try:
        target = os.readlink(comp, dir_fd=parent_fd)
    except OSError as exc:
        raise UnsafePathError(
            f"cannot read symlink {comp!r} in {str(path)!r}: {exc}"
        ) from exc
    target_parts = [part for part in target.split("/") if part not in ("", "/")]
    if os.path.isabs(target):
        # Absolute target: restart the walk from "/" (resolved_parts reset).
        for fd in fd_stack[1:]:
            try:
                os.close(fd)
            except OSError:
                pass
        del fd_stack[1:]
        resolved_parts.clear()
    pending[:0] = target_parts
    return hops


def ensure_parent_within(
    path: PathLike,
    allowed_roots: Optional[Iterable[PathLike]],
    *,
    base: Optional[PathLike] = None,
) -> Path:
    """Create missing parent directories of *path* via descriptors.

    Walks the existing parent components on descriptors (resolving
    symlinks via ``os.readlink`` with ``dir_fd``), computes the resolved
    final path, and refuses *before creating anything* if that path
    escapes the roots. Missing parent components are then created one
    by one with ``os.mkdir`` on the held parent descriptor; if anything
    appears at a to-be-created name in between, ``mkdir`` fails with
    ``EEXIST`` and the operation is refused rather than followed.
    Returns the resolved final path. Raises :class:`UnsafePathError`
    on escape, :class:`UnsupportedPlatformError` without descriptor
    opens.
    """
    _require_descriptor_open()
    candidate = Path(os.fspath(path)).expanduser()
    if not candidate.is_absolute() and base is not None:
        candidate = Path(os.fspath(base)).expanduser() / candidate
    if not candidate.is_absolute():
        candidate = Path(os.getcwd()) / candidate
    parts = [part for part in candidate.parts[1:] if part not in ("", "/")]
    if not parts:
        raise UnsafePathError(f"path {str(path)!r} has no final component")
    roots = resolve_allowed_roots(allowed_roots)
    parent_parts, final_name = parts[:-1], parts[-1]

    root_fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    fd_stack: List[int] = [root_fd]
    resolved_parts: List[str] = []
    missing: List[str] = []
    hops = 0
    try:
        pending: List[str] = list(parent_parts)
        steps = 0
        while pending:
            steps += 1
            if steps > _MAX_WALK_STEPS:
                raise UnsafePathError(f"path {str(path)!r} exceeds walk step limit")
            comp = pending.pop(0)
            if comp in ("", "."):
                continue
            if comp == "..":
                if resolved_parts:
                    resolved_parts.pop()
                    _close_all([fd_stack.pop()])
                continue
            parent_fd = fd_stack[-1]
            try:
                child = os.open(
                    comp,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                # O_DIRECTORY|O_NOFOLLOW on a symlink yields ENOTDIR,
                # not ELOOP, on Linux: check explicitly.
                if exc.errno in (errno.ELOOP, errno.ENOTDIR) and _is_symlink_at(
                    parent_fd, comp
                ):
                    hops = _follow_symlink(
                        parent_fd,
                        comp,
                        pending,
                        fd_stack,
                        resolved_parts,
                        hops,
                        path,
                    )
                    continue
                if exc.errno == errno.ENOENT:
                    # Rest of the parent chain is missing: stop walking
                    # (creation happens below, after containment).
                    missing = [comp, *pending]
                    break
                raise
            fd_stack.append(child)
            resolved_parts.append(comp)
        resolved_final = Path(
            os.sep + os.sep.join([*resolved_parts, *missing, final_name])
        )
        if roots and not any(
            resolved_final == root or resolved_final.is_relative_to(root)
            for root in roots
        ):
            raise UnsafePathError(
                f"path {str(path)!r} resolves to {resolved_final} which is "
                f"outside the allowed roots: {[str(r) for r in roots]}"
            )
        for comp in missing:
            parent_fd = fd_stack[-1]
            try:
                os.mkdir(comp, 0o755, dir_fd=parent_fd)
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    raise UnsafePathError(
                        f"parent component {comp!r} of {str(path)!r} "
                        "appeared during creation"
                    ) from exc
                raise
            child = os.open(
                comp,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
            fd_stack.append(child)
            resolved_parts.append(comp)
        return resolved_final
    finally:
        _close_all(fd_stack)


def open_within(
    path: PathLike,
    allowed_roots: Optional[Iterable[PathLike]],
    *,
    base: Optional[PathLike] = None,
    flags: int,
    mode: int = 0o666,
) -> Tuple[int, Path]:
    """Open *path* via descriptors, contained in *allowed_roots*.

    Returns ``(fd, resolved_path)``; the caller owns ``fd``. The open
    uses ``os.open(..., dir_fd=...)`` on the walked parent
    descriptor with ``O_NOFOLLOW``,
    then verifies the opened file is the one the walk saw (dev/ino, and
    the ``/proc/self/fd`` path where available). A symlink or file
    swapped in after the walk is refused, not followed.
    """
    parent_fd, final_name, resolved, expected = _fd_walk(path, allowed_roots, base=base)
    try:
        fd = os.open(
            final_name,
            flags | os.O_NOFOLLOW | os.O_CLOEXEC,
            mode,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise UnsafePathError(
                f"final component of {str(path)!r} became a symlink during open"
            ) from exc
        if exc.errno == errno.EEXIST:
            raise UnsafePathError(
                f"final component of {str(path)!r} appeared during open"
            ) from exc
        raise
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass
    try:
        if expected is None and not (flags & os.O_CREAT):
            # The walk found no file, but the open succeeded: the file
            # appeared between the walk's stat and the open. Without
            # O_CREAT the open should have failed, so this is a race
            # (a swapped-in victim). Refuse without touching it — in
            # particular, never ftruncate it.
            raise UnsafePathError(
                f"file {str(path)!r} appeared during open"
            )
        if expected is not None:
            actual = os.fstat(fd)
            if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                raise UnsafePathError(f"file {str(path)!r} was replaced during open")
        # Best-effort cross-check: the kernel's view of the fd must be
        # the resolved path the walk authorised.
        try:
            fd_path = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            fd_path = None
        if fd_path is not None and not fd_path.endswith(" (deleted)"):
            if Path(fd_path) != resolved:
                raise UnsafePathError(
                    f"opened fd for {str(path)!r} points at {fd_path}, "
                    f"not the authorised {resolved}"
                )
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return fd, resolved


def read_bytes_within(
    path: PathLike,
    allowed_roots: Optional[Iterable[PathLike]],
    *,
    base: Optional[PathLike] = None,
) -> Tuple[bytes, Path]:
    """Read a regular file via :func:`open_within`; return (bytes, resolved)."""
    fd, resolved = open_within(path, allowed_roots, base=base, flags=os.O_RDONLY)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise IsADirectoryError(f"not a regular file: {str(path)!r}")
        chunks: List[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), resolved
    finally:
        os.close(fd)


def open_for_write_within(
    path: PathLike,
    allowed_roots: Optional[Iterable[PathLike]],
    *,
    base: Optional[PathLike] = None,
    append: bool = False,
    create: bool = False,
) -> Tuple[int, Path]:
    """Open *path* for writing via descriptors; return (fd, resolved).

    Existing files are truncated (or appended to with ``append=True``).
    With ``create=True`` a missing file is created with
    ``O_CREAT | O_EXCL`` — a symlink or file appearing in between is
    refused rather than followed or truncated.

    Non-destructive: the file is opened WITHOUT ``O_TRUNC`` first;
    the descriptor is validated (dev/ino + containment) by
    :func:`open_within`, and only then is it truncated with
    :func:`os.ftruncate` on the verified fd. A swapped victim file is
    therefore refused with its bytes intact — the old code passed
    ``O_TRUNC`` into the open, so a swapped-in file was truncated to
    ``""`` before the dev/ino check rejected it.
    """
    if append:
        # O_APPEND never truncates, so the open itself is non-destructive.
        flags = os.O_WRONLY | os.O_APPEND
        try:
            return open_within(path, allowed_roots, base=base, flags=flags)
        except FileNotFoundError:
            if not create:
                raise
            return open_within(
                path,
                allowed_roots,
                base=base,
                flags=flags | os.O_CREAT | os.O_EXCL,
                mode=0o666,
            )
    # Truncate path: open without O_TRUNC, validate, then ftruncate.
    try:
        fd, resolved = open_within(
            path, allowed_roots, base=base, flags=os.O_WRONLY
        )
    except FileNotFoundError:
        if not create:
            raise
        # Create: O_EXCL, no O_TRUNC (a newly created file is empty;
        # nothing to truncate, and O_EXCL refuses a raced-in file).
        return open_within(
            path,
            allowed_roots,
            base=base,
            flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            mode=0o666,
        )
    try:
        os.ftruncate(fd, 0)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return fd, resolved


def open_rdwr_within(
    path: PathLike,
    allowed_roots: Optional[Iterable[PathLike]],
    *,
    base: Optional[PathLike] = None,
) -> Tuple[int, Path]:
    """Open an existing file read/write via descriptors; return (fd, resolved)."""
    return open_within(path, allowed_roots, base=base, flags=os.O_RDWR)


__all__ = [
    "UnsupportedPlatformError",
    "UnsafePathError",
    "ensure_parent_within",
    "is_within",
    "open_for_write_within",
    "open_rdwr_within",
    "open_within",
    "read_bytes_within",
    "resolve_allowed_roots",
    "resolve_within",
]
