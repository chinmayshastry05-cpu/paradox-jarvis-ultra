"""File write tool — write content to files with path validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._paths import resolve_allowed_dirs
from openjarvis.tools._stubs import BaseTool, ToolSpec

# Maximum file size to write (10 MB)
_MAX_SIZE_BYTES = 10_485_760


@ToolRegistry.register("file_write")
class FileWriteTool(BaseTool):
    """Write content to files with optional directory restrictions."""

    tool_id = "file_write"

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
            name="file_write",
            description=("Write content to a file. Supports write and append modes."),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file.",
                    },
                    "mode": {
                        "type": "string",
                        "description": (
                            "Write mode: 'write' (overwrite/create)"
                            " or 'append' (append to existing)."
                            " Default: 'write'."
                        ),
                    },
                    "create_dirs": {
                        "type": "boolean",
                        "description": (
                            "Create parent directories if they"
                            " don't exist. Default: false."
                        ),
                    },
                },
                "required": ["path", "content"],
            },
            category="filesystem",
            required_capabilities=["file:write"],
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
                tool_name="file_write",
                content="No path provided.",
                success=False,
            )

        content = params.get("content")
        if content is None:
            return ToolResult(
                tool_name="file_write",
                content="No content provided.",
                success=False,
            )

        mode = params.get("mode", "write")
        if mode not in ("write", "append"):
            return ToolResult(
                tool_name="file_write",
                content=f"Invalid mode: {mode!r}. Use 'write' or 'append'.",
                success=False,
            )

        create_dirs = params.get("create_dirs", False)

        path = Path(file_path)
        if not path.is_absolute() and self._allowed_dirs:
            # A relative name means "inside the sandbox", not the process cwd.
            path = self._allowed_dirs[0] / path

        # Block sensitive files (secrets, credentials, keys)
        from openjarvis.security.file_policy import is_sensitive_file

        if is_sensitive_file(path):
            return ToolResult(
                tool_name="file_write",
                content=f"Access denied: {file_path} is a sensitive file.",
                success=False,
            )

        # Check content size before writing
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > _MAX_SIZE_BYTES:
            return ToolResult(
                tool_name="file_write",
                content=(
                    f"Content too large: {len(content_bytes)} bytes"
                    f" (max {_MAX_SIZE_BYTES})."
                ),
                success=False,
            )

        import os

        from openjarvis.security.canonical_path import (
            UnsafePathError,
            UnsupportedPlatformError,
            ensure_parent_within,
            open_for_write_within,
        )

        # Parent directories: created via descriptors when requested,
        # never by following a string path. Without create_dirs a
        # missing parent is an error, as before.
        if create_dirs:
            try:
                ensure_parent_within(path, self._allowed_dirs)
            except UnsafePathError:
                return ToolResult(
                    tool_name="file_write",
                    content=(
                        f"Access denied: {file_path} is outside allowed directories."
                    ),
                    success=False,
                )
            except UnsupportedPlatformError:
                if self._allowed_dirs:
                    return ToolResult(
                        tool_name="file_write",
                        content=(
                            f"Access denied: {file_path} cannot be opened "
                            "safely on this platform."
                        ),
                        success=False,
                    )
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    return ToolResult(
                        tool_name="file_write",
                        content=f"Cannot create directories: {exc}",
                        success=False,
                    )
            except OSError as exc:
                return ToolResult(
                    tool_name="file_write",
                    content=f"Cannot create directories: {exc}",
                    success=False,
                )

        # Open via descriptors: containment, symlink resolution and
        # the open are one operation. The Rust path-based writer is
        # deliberately not used: it would re-open by string and
        # re-introduce the race.
        try:
            fd, resolved = open_for_write_within(
                path,
                self._allowed_dirs,
                append=(mode == "append"),
                create=True,
            )
        except UnsafePathError:
            return ToolResult(
                tool_name="file_write",
                content=f"Access denied: {file_path} is outside allowed directories.",
                success=False,
            )
        except UnsupportedPlatformError:
            if self._allowed_dirs:
                return ToolResult(
                    tool_name="file_write",
                    content=(
                        f"Access denied: {file_path} cannot be opened "
                        "safely on this platform."
                    ),
                    success=False,
                )
            return self._legacy_write(path, file_path, content_bytes)
        except FileNotFoundError:
            return ToolResult(
                tool_name="file_write",
                content=(
                    f"Parent directory does not exist: {path.parent}."
                    " Set create_dirs=true to create it."
                ),
                success=False,
            )
        except IsADirectoryError:
            return ToolResult(
                tool_name="file_write",
                content=f"Not a file: {file_path}",
                success=False,
            )
        except OSError as exc:
            return ToolResult(
                tool_name="file_write",
                content=f"Write error: {exc}",
                success=False,
            )
        try:
            view = memoryview(content_bytes)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            size = os.fstat(fd).st_size
        except OSError as exc:
            return ToolResult(
                tool_name="file_write",
                content=f"Write error: {exc}",
                success=False,
            )
        finally:
            os.close(fd)
        return ToolResult(
            tool_name="file_write",
            content=f"Successfully wrote to {file_path}",
            success=True,
            metadata={"path": str(resolved), "size_bytes": size},
        )

    def _legacy_write(self, path, file_path, content_bytes):
        """Plain string write, only when no boundary is configured and
        the platform has no descriptor open. No containment is claimed."""
        try:
            path.write_bytes(content_bytes)
        except OSError as exc:
            return ToolResult(
                tool_name="file_write",
                content=f"Write error: {exc}",
                success=False,
            )
        try:
            size = path.stat().st_size
        except OSError:
            size = len(content_bytes)
        return ToolResult(
            tool_name="file_write",
            content=f"Successfully wrote to {file_path}",
            success=True,
            metadata={"path": str(path), "size_bytes": size},
        )


__all__ = ["FileWriteTool"]
