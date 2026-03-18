"""
Shared utilities for Django management commands.

Used by §10 management-commands inventory and deprecation policy
(BACKLOG §2e row 9; management_commands_inventory.md).
"""

from __future__ import annotations

from typing import Any, Optional


def emit_command_deprecation(
    stdout: Any,
    style: Any,
    message: str,
    replacement: Optional[str] = None,
) -> None:
    """
    Write a deprecation warning to the command stdout.

    Use at the start of handle() for deprecated management commands so
    callers (CI, scripts, humans) see the warning. Document the replacement
    in the command docstring and in docs/management_commands_inventory.md.

    Args:
        stdout: Command's self.stdout (has write()).
        style: Command's self.style (has WARNING(), SUCCESS()).
        message: Short deprecation message (e.g. "Command X is deprecated.").
        replacement: Optional "Use instead: ..." or "Replacement: ..." text.
    """
    stdout.write(style.WARNING(f"Deprecation: {message}"))
    if replacement:
        stdout.write(style.WARNING(f"  Replacement: {replacement}"))
