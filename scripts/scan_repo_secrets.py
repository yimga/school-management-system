#!/usr/bin/env python3
"""
Fail fast on high-risk secret patterns in committed source (complements lint_secret_exposure.py).

Scans text files under apps/, config/, services/ — excludes migrations, __pycache__, static vendor.
Exit 0 = no matches; exit 1 = findings.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("apps", "config", "services")
SKIP_PARTS = frozenset(
    {
        "migrations",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
    }
)
# Patterns that strongly suggest committed credentials (not exhaustive).
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "AWS access key (20 chars)",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "Stripe live secret",
        re.compile(r"\bsk_live_[0-9a-zA-Z]{20,}\b"),
    ),
    (
        "GitHub classic PAT (ghp_)",
        re.compile(r"\bghp_[0-9a-zA-Z]{30,}\b"),
    ),
    (
        "GitHub fine-grained PAT (github_pat_)",
        re.compile(r"\bgithub_pat_[0-9a-zA-Z_]{20,}\b"),
    ),
]


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for name in SCAN_ROOTS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            parts = set(p.parts)
            if parts & SKIP_PARTS:
                continue
            if p.suffix.lower() not in {".py", ".html", ".js", ".ts", ".tsx", ".yml", ".yaml", ".json", ".md", ".sh"}:
                continue
            out.append(p)
    return out


def main() -> int:
    bad: list[str] = []
    for path in _iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for label, rx in PATTERNS:
            if rx.search(text):
                # Allow obvious placeholders in docs/tests
                if "/tests/" in str(path).replace("\\", "/") and "AKIA" in label:
                    if "EXAMPLE" in text or "placeholder" in text.lower():
                        continue
                bad.append(f"{path.relative_to(ROOT)}: possible {label}")

    if bad:
        print("scan_repo_secrets: potential secret-like strings found:", file=sys.stderr)
        for line in bad[:50]:
            print(f"  {line}", file=sys.stderr)
        if len(bad) > 50:
            print(f"  ... and {len(bad) - 50} more", file=sys.stderr)
        return 1
    print("scan_repo_secrets: OK (no high-risk patterns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
