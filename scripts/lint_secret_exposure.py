#!/usr/bin/env python3
"""
Block provider secret exposure in client assets and tracked env/config files.

Checks:
- secret identifiers must not appear in client-rendered templates or frontend assets
- context processors must not expose provider secret keys to templates
- tracked env files must not contain non-empty provider secret assignments
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIRS = ("templates", "frontend", "static")
SECRET_NAMES = (
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "MISTRAL_API_KEY",
)
SECRET_NAME_PATTERN = re.compile(r"\b(" + "|".join(re.escape(name) for name in SECRET_NAMES) + r")\b")
ENV_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*(" + "|".join(re.escape(name) for name in SECRET_NAMES) + r")\s*=\s*(.+?)\s*$"
)
PLACEHOLDER_TOKENS = ("", "changeme", "replace_me", "your_", "<", "example", "placeholder")


def _tracked_root_env_files() -> list[Path]:
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    files: list[Path] = []
    for rel in proc.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        path = ROOT / rel
        if path.name.startswith(".env") or path.suffix in {".env", ".yaml", ".yml"}:
            files.append(path)
    return files


def _client_files() -> list[Path]:
    files: list[Path] = []
    for dirname in CLIENT_DIRS:
        base = ROOT / dirname
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".html", ".js", ".jsx", ".ts", ".tsx"}:
                continue
            files.append(path)
    return files


def _context_processor_files() -> list[Path]:
    files: list[Path] = []
    apps_dir = ROOT / "apps"
    if not apps_dir.is_dir():
        return files
    for path in apps_dir.rglob("context_processors.py"):
        files.append(path)
    return files


def main() -> int:
    violations: list[str] = []

    for path in _client_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if SECRET_NAME_PATTERN.search(line):
                rel = path.relative_to(ROOT).as_posix()
                violations.append(f"{rel}:{line_no} references a provider secret name in client-rendered code")

    for path in _context_processor_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if SECRET_NAME_PATTERN.search(line):
                rel = path.relative_to(ROOT).as_posix()
                violations.append(f"{rel}:{line_no} references a provider secret name in a context processor")

    for path in _tracked_root_env_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            match = ENV_ASSIGNMENT_PATTERN.match(line)
            if not match:
                continue
            value = match.group(2).strip().strip("'\"")
            lowered = value.lower()
            if any(token and token in lowered for token in PLACEHOLDER_TOKENS[3:]):
                continue
            if lowered in PLACEHOLDER_TOKENS[:3] or not value:
                continue
            violations.append(f"{rel}:{line_no} contains a non-placeholder provider secret assignment")

    if violations:
        print("lint_secret_exposure: violations detected:\n", file=sys.stderr)
        for violation in sorted(violations):
            print(f"  {violation}", file=sys.stderr)
        return 1

    print("lint_secret_exposure: no client-side or tracked-config provider secret exposure found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
