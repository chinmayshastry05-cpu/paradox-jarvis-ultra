"""Shared TTY confirmation prompt for tool execution.

The single place CLI entry points obtain a human yes/no for a tool
that requires confirmation. Anything that cannot prompt a human —
non-TTY stdin, EOF, abort — denies. There is no auto-approve path:
a callback that always returns True is a confirmation bypass, not a
confirmation.
"""

from __future__ import annotations

import click


def confirm_tool(prompt: str) -> bool:
    """Ask the user to approve one tool execution. Defaults to NO."""
    try:
        return bool(click.confirm(f"\n{prompt}", default=False))
    except (click.Abort, EOFError, KeyboardInterrupt):
        return False


__all__ = ["confirm_tool"]
