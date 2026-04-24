from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Workspace root (directory containing ``apps/`` and ``scripts/``)."""
    return Path(__file__).resolve().parents[4]
