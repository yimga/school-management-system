#!/usr/bin/env python3
"""
Remove git merge conflict markers from all .py files in the project.
Keeps the HEAD version between <<<<<<< and =======; drops ======= to >>>>>>>.
Run from project root: python scripts/remove_merge_conflict_markers.py
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "venv", "env", ".git", "__pycache__", "node_modules", ".tox"}


def remove_conflict_markers(content: str) -> str:
    """Remove <<<<<<< HEAD, =======, >>>>>>> branch lines and keep HEAD version."""
    lines = content.splitlines(keepends=True)
    out = []
    in_conflict = False
    keep_until_equals = False
    for line in lines:
        if line.strip().startswith("<<<<<<<"):
            in_conflict = True
            keep_until_equals = True
            continue
        if line.strip().startswith("======="):
            keep_until_equals = False
            continue
        if line.strip().startswith(">>>>>>>"):
            in_conflict = False
            continue
        if in_conflict and keep_until_equals:
            out.append(line)
        elif not in_conflict:
            out.append(line)
    return "".join(out)


def py_files(root: Path):
    """Yield all .py files under root, skipping SKIP_DIRS."""
    for path in root.rglob("*.py"):
        if any(part in path.parts for part in SKIP_DIRS):
            continue
        yield path


def main():
    cleaned = []
    for path in py_files(PROJECT_ROOT):
        if path == Path(__file__).resolve():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Skip {path}: {e}")
            continue
        if "<<<<<<<" not in content and ">>>>>>>" not in content:
            continue
        fixed = remove_conflict_markers(content)
        path.write_text(fixed, encoding="utf-8")
        cleaned.append(path.relative_to(PROJECT_ROOT))
    if not cleaned:
        print("No conflict markers found in any .py file.")
        return 0
    print("Removed conflict markers from:")
    for p in cleaned:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
