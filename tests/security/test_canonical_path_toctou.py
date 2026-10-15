"""TOCTOU regression tests for descriptor-based opens.

The old pattern (``resolve_within`` then open by string) loses to a
racing attacker who swaps a path component between the check and the
open. These tests attack the open itself: a symlink flipped rapidly
between an inside and an outside target must never yield the outside
file, and a file swapped between walk and open must be refused.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from openjarvis.security.canonical_path import (
    UnsafePathError,
    UnsupportedPlatformError,
    ensure_parent_within,
    open_for_write_within,
    read_bytes_within,
)


def test_open_within_reads_inside_symlink_target(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "real.txt"
    target.write_text("inside", encoding="utf-8")
    link = allowed / "alias.txt"
    link.symlink_to(target)
    data, resolved = read_bytes_within(link, [allowed])
    assert data == b"inside"
    assert resolved == target


def test_open_within_refuses_final_symlink_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = allowed / "escape.txt"
    link.symlink_to(outside)
    with pytest.raises(UnsafePathError):
        read_bytes_within(link, [allowed])
    assert outside.read_text(encoding="utf-8") == "outside"


def test_open_within_refuses_intermediate_symlink_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "f.txt").write_text("outside", encoding="utf-8")
    link_dir = tmp_path / "linkdir"
    link_dir.symlink_to(outside_dir, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        read_bytes_within(link_dir / "f.txt", [allowed])
    # The old string-check also rejected this; the open must too.
    with pytest.raises(UnsafePathError):
        read_bytes_within(allowed / ".." / "outside_dir" / "f.txt", [allowed])


def test_open_within_refuses_symlink_loop(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    a = allowed / "a"
    b = allowed / "b"
    a.symlink_to(b)
    b.symlink_to(a)
    with pytest.raises(UnsafePathError):
        read_bytes_within(a, [allowed])


def test_open_within_dangling_symlink_to_inside_creates_there(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    real = allowed / "real.txt"
    link = allowed / "new.txt"
    link.symlink_to(real)  # dangling: real does not exist yet
    fd, resolved = open_for_write_within(link, [allowed], create=True)
    try:
        os.write(fd, b"created")
    finally:
        os.close(fd)
    assert resolved == real
    assert real.read_bytes() == b"created"
    assert link.is_symlink()  # the symlink itself is untouched


def test_create_never_follows_symlink_to_outside(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("original", encoding="utf-8")
    link = allowed / "new.txt"
    link.symlink_to(outside)
    with pytest.raises(UnsafePathError):
        open_for_write_within(link, [allowed], create=True)
    assert outside.read_text(encoding="utf-8") == "original"


def test_ensure_parent_creates_nested_and_refuses_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    resolved = ensure_parent_within(allowed / "a" / "b" / "f.txt", [allowed])
    assert resolved == allowed / "a" / "b" / "f.txt"
    assert (allowed / "a" / "b").is_dir()

    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    link_dir = allowed / "linkdir"
    link_dir.symlink_to(outside_dir, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        ensure_parent_within(link_dir / "new" / "f.txt", [allowed])
    assert not (outside_dir / "new").exists()


def test_unsupported_platform_refuses(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(os, "supports_dir_fd", set())
    with pytest.raises(UnsupportedPlatformError):
        read_bytes_within(tmp_path / "f.txt", [tmp_path])


def _flip_symlink(
    stop: threading.Event, link: Path, inside: Path, outside: Path
) -> None:
    """Atomically flip *link* between the inside and outside targets."""
    tmp = link.with_name(".flip-tmp")
    i = 0
    while not stop.is_set():
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        tmp.symlink_to(inside if i % 2 == 0 else outside)
        os.replace(tmp, link)
        i += 1


def test_racing_symlink_flip_never_leaks_outside(tmp_path: Path) -> None:
    """Adversarial: attacker flips a symlink while reads are in flight."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    inside = allowed / "inside.txt"
    inside.write_text("inside-content", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE-CONTENT", encoding="utf-8")
    link = allowed / "flip.txt"
    link.symlink_to(inside)

    stop = threading.Event()
    attacker = threading.Thread(
        target=_flip_symlink, args=(stop, link, inside, outside), daemon=True
    )
    attacker.start()
    try:
        successes = 0
        for _ in range(300):
            try:
                data, _ = read_bytes_within(link, [allowed])
            except UnsafePathError:
                continue  # refused: safe outcome
            assert data == b"inside-content", data
            successes += 1
    finally:
        stop.set()
        attacker.join(timeout=5)
    # The attacker flipped continuously; at least some reads must have
    # landed on the inside target (otherwise the test proved nothing).
    assert successes > 0


def test_racing_create_never_writes_outside(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("original", encoding="utf-8")
    inside_target = allowed / "created.txt"
    link = allowed / "new.txt"
    link.symlink_to(inside_target)

    stop = threading.Event()
    attacker = threading.Thread(
        target=_flip_symlink, args=(stop, link, inside_target, outside), daemon=True
    )
    attacker.start()
    try:
        for _ in range(200):
            try:
                fd, _ = open_for_write_within(link, [allowed], create=True)
            except (UnsafePathError, FileExistsError, FileNotFoundError, OSError):
                continue
            try:
                os.write(fd, b"x")
            finally:
                os.close(fd)
            # The writer may have created inside_target; remove it so
            # the next iteration exercises creation again.
            if inside_target.exists():
                inside_target.unlink()
    finally:
        stop.set()
        attacker.join(timeout=5)
    assert outside.read_text(encoding="utf-8") == "original"


def test_file_write_refuses_dangling_symlink_to_outside(tmp_path: Path) -> None:
    from openjarvis.tools.file_write import FileWriteTool

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("original", encoding="utf-8")
    link = allowed / "new.txt"
    link.symlink_to(outside)
    # Dangling (outside exists, but the write must not follow it).
    result = FileWriteTool(allowed_dirs=[str(allowed)]).execute(
        path=str(link), content="pwned", mode="write"
    )
    assert result.success is False
    assert outside.read_text(encoding="utf-8") == "original"


def _swap_before_final_open(monkeypatch, target: Path, replacement: Path) -> None:
    """Monkeypatch os.open to os.replace(replacement -> target) on the
    first final-component open of *target*, then call the real open.

    Mirrors the reviewer's injection: the swap lands immediately before
    the final ``os.open(dir_fd=...)``. Also keeps the wrapper inside
    ``os.supports_dir_fd`` so the descriptor-open check still passes.
    """
    real_open = os.open
    calls = {"n": 0}

    def swapping_open(path, flags, *args, **kwargs):
        if (
            isinstance(path, str)
            and path == target.name
            and not (flags & os.O_DIRECTORY)
        ):
            calls["n"] += 1
            if calls["n"] == 1:
                os.replace(str(replacement), str(target))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swapping_open)
    monkeypatch.setattr(
        os, "supports_dir_fd", set(os.supports_dir_fd) | {swapping_open}
    )


def test_write_truncate_refuses_swap_without_destroying_victim(
    tmp_path: Path, monkeypatch
) -> None:
    """Destructive-TOCTOU regression: O_TRUNC must not precede validation.

    The old code passed O_TRUNC into the open, so a swapped-in victim
    file was truncated to '' before the dev/ino check rejected it.
    The fix opens without O_TRUNC, validates, then ftruncates the
    verified fd. The regression asserts victim bytes unchanged — not
    merely that an exception was raised.
    """
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "target.txt"
    target.write_text("original-target", encoding="utf-8")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("VICTIM-CONTENT", encoding="utf-8")
    _swap_before_final_open(monkeypatch, target, replacement)
    with pytest.raises(UnsafePathError):
        open_for_write_within(target, [allowed])
    assert target.read_text(encoding="utf-8") == "VICTIM-CONTENT"


def test_write_append_refuses_swap_without_destroying_victim(
    tmp_path: Path, monkeypatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "target.txt"
    target.write_text("original-target", encoding="utf-8")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("VICTIM-CONTENT", encoding="utf-8")
    _swap_before_final_open(monkeypatch, target, replacement)
    with pytest.raises(UnsafePathError):
        open_for_write_within(target, [allowed], append=True)
    assert target.read_text(encoding="utf-8") == "VICTIM-CONTENT"


def test_write_create_refuses_file_appearing_during_open(
    tmp_path: Path, monkeypatch
) -> None:
    """A file appearing between walk and open is refused, not truncated.

    The walk found no file (expected is None); the first O_WRONLY open
    must fail, and the create retry must not truncate a raced-in file.
    """
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "new.txt"  # does not exist at walk time
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("VICTIM-CONTENT", encoding="utf-8")
    _swap_before_final_open(monkeypatch, target, replacement)
    with pytest.raises(UnsafePathError):
        open_for_write_within(target, [allowed], create=True)
    assert target.read_text(encoding="utf-8") == "VICTIM-CONTENT"


def test_write_unsupported_platform_refuses_without_touching_file(
    tmp_path: Path, monkeypatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "f.txt"
    target.write_text("ORIGINAL", encoding="utf-8")
    monkeypatch.setattr(os, "supports_dir_fd", set())
    with pytest.raises(UnsupportedPlatformError):
        open_for_write_within(target, [allowed])
    assert target.read_text(encoding="utf-8") == "ORIGINAL"


def test_write_truncate_still_truncates_legitimate_file(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "f.txt"
    target.write_text("OLD-CONTENT", encoding="utf-8")
    fd, _ = open_for_write_within(target, [allowed])
    try:
        os.write(fd, b"NEW")
    finally:
        os.close(fd)
    assert target.read_text(encoding="utf-8") == "NEW"


def test_apply_patch_uses_held_fd(tmp_path: Path) -> None:
    from openjarvis.tools.apply_patch import ApplyPatchTool

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "f.txt"
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    patch = (
        "--- a/f.txt\n+++ b/f.txt\n@@ -1,3 +1,3 @@\n line1\n-line2\n+patched\n line3\n"
    )
    result = ApplyPatchTool(allowed_dirs=[str(allowed)]).execute(
        path=str(target), patch=patch
    )
    assert result.success is True
    assert target.read_text(encoding="utf-8") == "line1\npatched\nline3\n"
    assert (allowed / "f.txt.bak").read_text(encoding="utf-8") == (
        "line1\nline2\nline3\n"
    )
