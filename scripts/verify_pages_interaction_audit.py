#!/usr/bin/env python3
"""
Audit static/js/_pages/*.js for interaction hygiene (stdlib-only).

Checks each page script for:
  - no bare ``console.log`` (use structured handlers / guards)
  - fetch URLs are absolute-path API routes (not dead ``#`` or empty)
  - file parses as JavaScript (node syntax check when available)

Writes docs/generated/pages_interaction_audit.json
Exit 0 when all checks pass.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "static" / "js" / "_pages"
OUT = ROOT / "docs" / "generated" / "pages_interaction_audit.json"

FETCH_RE = re.compile(r"""fetch\s*\(\s*['"]([^'"]+)['"]""")
CONSOLE_LOG_RE = re.compile(r"\bconsole\.log\s*\(")


def _audit_file(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    if CONSOLE_LOG_RE.search(text):
        issues.append(f"{rel}: console.log")
    for match in FETCH_RE.finditer(text):
        url = match.group(1).strip()
        if url in ("#", ""):
            issues.append(f"{rel}: dead fetch url {url!r}")
        if url.startswith("http://") or url.startswith("https://"):
            issues.append(f"{rel}: off-origin fetch {url}")
    return issues


def _syntax_check(path: Path) -> str | None:
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        return None
    try:
        proc = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "node check timeout"
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or "syntax error").strip()[-200:]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not PAGES_DIR.is_dir():
        print("verify_pages_interaction_audit: missing _pages directory", file=sys.stderr)
        return 1

    files = sorted(PAGES_DIR.glob("*.js"))
    issues: list[str] = []
    syntax_errors: list[str] = []
    for path in files:
        issues.extend(_audit_file(path))
        err = _syntax_check(path)
        if err:
            syntax_errors.append(f"{path.relative_to(ROOT).as_posix()}: {err}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PAGES_INTERACTION_AUDIT_PASS"
        if not issues and not syntax_errors
        else "PAGES_INTERACTION_AUDIT_FAIL",
        "file_count": len(files),
        "issue_count": len(issues) + len(syntax_errors),
        "issues": issues[:50],
        "syntax_errors": syntax_errors[:20],
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(payload["status"], f"files={len(files)} issues={payload['issue_count']}")
    for item in issues[:10]:
        print(f"  - {item}", file=sys.stderr)
    for item in syntax_errors[:5]:
        print(f"  - syntax: {item}", file=sys.stderr)
    return 0 if payload["status"].endswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
