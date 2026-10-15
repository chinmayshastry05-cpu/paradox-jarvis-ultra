"""Canonical path / symlink checks for file tool paths.

Every filesystem tool must resolve symlinks (including symlinks in
parent directories) *before* deciding whether a path is allowed, and
reject any path whose resolved form escapes the configured allowed
roots. Checking the unresolved user-supplied string is not enough: a
symlink inside an allowed root can point anywhere on the filesystem.

TOCTOU note: resolving then opening still leaves a small window in
which a path could be swapped for a symlink between the check and the
open. The check closes the deterministic escape (a pre-existing symlink
or ``..`` traversal); it does not claim to close a racing attacker who
can rewrite the filesystem between check and use.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional, Union

PathLike = Union[str, os.PathLike]


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
    raise ValueError(
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


__all__ = ["is_within", "resolve_allowed_roots", "resolve_within"]
