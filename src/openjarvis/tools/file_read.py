"""File read tool — read file contents with path validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._paths import resolve_allowed_dirs
from openjarvis.tools._stubs import BaseTool, ToolSpec

# Maximum file size to read (1 MB)
_MAX_SIZE_BYTES = 1_048_576


@ToolRegistry.register("file_read")
class FileReadTool(BaseTool):
    """Read file contents with optional directory restrictions."""

    tool_id = "file_read"

    def __init__(
        self,
        allowed_dirs: Optional[List[str]] = None,
    ) -> None:
        self._allowed_dirs = [
            Path(d).expanduser().resolve() for d in resolve_allowed_dirs(allowed_dirs)
        ]

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="file_read",
            description=("Read the contents of a file. Returns the text content."),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read.",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": ("Max lines to return (default: all)."),
                    },
                },
                "required": ["path"],
            },
            category="filesystem",
        )

    def _is_path_allowed(self, path: Path) -> bool:
        """Pre-check only (see :mod:`openjarvis.security.canonical_path`).

        Authorisation happens in :func:`open_within` at open time;
        this helper exists for callers that need a cheap pre-check.
        """
        from openjarvis.security.canonical_path import is_within

        return is_within(path, self._allowed_dirs)

    def execute(self, **params: Any) -> ToolResult:
        file_path = params.get("path", "")
        if not file_path:
            return ToolResult(
                tool_name="file_read",
                content="No path provided.",
                success=False,
            )
        path = Path(file_path)
        if not path.is_absolute() and self._allowed_dirs:
            # A relative name means "inside the sandbox", not the process cwd.
            path = self._allowed_dirs[0] / path
        # Block sensitive files (secrets, credentials, keys)
        from openjarvis.security.file_policy import is_sensitive_file

        if is_sensitive_file(path):
            return ToolResult(
                tool_name="file_read",
                content=f"Access denied: {file_path} is a sensitive file.",
                success=False,
            )
        # Open via descriptors: containment, symlink resolution and the
        # open are one operation — a path swapped between a string
        # check and the open cannot redirect this read. The Rust
        # path-based reader is deliberately not used here: it would
        # re-open the path by string and re-introduce the race.
        import os
        import stat as _stat

        from openjarvis.security.canonical_path import (
            UnsafePathError,
            UnsupportedPlatformError,
            open_within,
        )

        try:
            fd, resolved = open_within(path, self._allowed_dirs, flags=os.O_RDONLY)
        except UnsafePathError:
            return ToolResult(
                tool_name="file_read",
                content=f"Access denied: {file_path} is outside allowed directories.",
                success=False,
            )
        except UnsupportedPlatformError:
            if self._allowed_dirs:
                # No safe open available and a boundary is configured:
                # refuse rather than fall back to a racy string open.
                return ToolResult(
                    tool_name="file_read",
                    content=(
                        f"Access denied: {file_path} cannot be opened "
                        "safely on this platform."
                    ),
                    success=False,
                )
            return self._legacy_read(path, file_path, params)
        except FileNotFoundError:
            return ToolResult(
                tool_name="file_read",
                content=f"File not found: {file_path}",
                success=False,
            )
        except IsADirectoryError:
            return ToolResult(
                tool_name="file_read",
                content=f"Not a file: {file_path}",
                success=False,
            )
        except OSError as exc:
            return ToolResult(
                tool_name="file_read",
                content=f"Read error: {exc}",
                success=False,
            )
        try:
            st = os.fstat(fd)
            if not _stat.S_ISREG(st.st_mode):
                return ToolResult(
                    tool_name="file_read",
                    content=f"Not a file: {file_path}",
                    success=False,
                )
            size = st.st_size
            if size > _MAX_SIZE_BYTES:
                return ToolResult(
                    tool_name="file_read",
                    content=f"File too large: {size} bytes (max {_MAX_SIZE_BYTES}).",
                    success=False,
                )
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
        except OSError as exc:
            return ToolResult(
                tool_name="file_read",
                content=f"Read error: {exc}",
                success=False,
            )
        finally:
            os.close(fd)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        max_lines = params.get("max_lines")
        if max_lines is not None and max_lines > 0:
            lines = text.splitlines(keepends=True)
            text = "".join(lines[:max_lines])
        return ToolResult(
            tool_name="file_read",
            content=text,
            success=True,
            metadata={"path": str(resolved), "size_bytes": size},
        )

    def _legacy_read(self, path, file_path, params):
        """Plain string open, only when no boundary is configured and the
        platform has no descriptor open. No containment is claimed."""
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolResult(
                tool_name="file_read",
                content=f"File not found: {file_path}",
                success=False,
            )
        except IsADirectoryError:
            return ToolResult(
                tool_name="file_read",
                content=f"Not a file: {file_path}",
                success=False,
            )
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(
                tool_name="file_read",
                content=f"Read error: {exc}",
                success=False,
            )
        max_lines = params.get("max_lines")
        if max_lines is not None and max_lines > 0:
            lines = text.splitlines(keepends=True)
            text = "".join(lines[:max_lines])
        try:
            size = path.stat().st_size
        except OSError:
            size = len(text.encode("utf-8"))
        return ToolResult(
            tool_name="file_read",
            content=text,
            success=True,
            metadata={"path": str(path), "size_bytes": size},
        )


__all__ = ["FileReadTool"]
