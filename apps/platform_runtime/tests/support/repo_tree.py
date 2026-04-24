from __future__ import annotations

from pathlib import Path


def write_repo_file(root: Path, rel: str, content: str) -> None:
    path = root / Path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
