#!/usr/bin/env python
"""Audit templates for user-facing placeholder content that should not ship.

Catches text that smells like an unfinished stub: "Lorem ipsum", "Coming soon",
"TODO", "Not implemented", "Sample data", "Replace me", "Placeholder text".

Excludes legitimate uses:
- HTML attribute `placeholder=""` on form inputs (input affordance, not stub copy)
- `# TODO:` / `{# TODO #}` developer notes (not user-visible)
- "No <thing> yet" empty-state copy (legitimate, polished)

Writes docs/generated/no_placeholder_audit.json and prints summary.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = ROOT / "templates"
OUT_PATH = ROOT / "docs" / "generated" / "no_placeholder_audit.json"

USER_VISIBLE_PATTERNS = [
    (re.compile(r"\blorem\s+ipsum\b", re.I), "lorem-ipsum"),
    (re.compile(r"\bComing\s+soon\b", re.I), "coming-soon"),
    (re.compile(r"\bNot\s+implemented\b", re.I), "not-implemented"),
    (re.compile(r"\bReplace\s+me\b", re.I), "replace-me"),
    (re.compile(r"\bPlaceholder\s+text\b", re.I), "placeholder-text"),
    (re.compile(r"\bSample\s+data\b", re.I), "sample-data"),
    (re.compile(r"\bFake\s+content\b", re.I), "fake-content"),
    (re.compile(r"\bunder\s+construction\b", re.I), "under-construction"),
    (re.compile(r"\bWork\s+in\s+progress\b", re.I), "work-in-progress"),
    (re.compile(r"\bTBD\b"), "tbd"),
    (re.compile(r"\bTBA\b"), "tba"),
]

DEV_NOTE_PATTERNS = [
    (re.compile(r"^\s*\{#.*TODO.*#\}\s*$"), "django-todo-comment"),
    (re.compile(r"\{%\s*comment\s*%\}.*TODO.*\{%\s*endcomment\s*%\}", re.I | re.S), "django-todo-comment-block"),
]

INPUT_PLACEHOLDER_ATTR = re.compile(r'\bplaceholder\s*=\s*"[^"]*"')

EXCLUDE_DIRS = {".git", "__pycache__", "node_modules"}


def is_user_visible_line(line: str) -> bool:
    """Strip HTML input placeholder attrs before checking; everything else counts."""
    stripped = INPUT_PLACEHOLDER_ATTR.sub("", line)
    for dev_pat, _ in DEV_NOTE_PATTERNS:
        if dev_pat.search(stripped):
            return False
    return True


def scan_template(path: Path) -> list[dict]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    for lineno, line in enumerate(text.splitlines(), 1):
        if not is_user_visible_line(line):
            continue
        for pat, kind in USER_VISIBLE_PATTERNS:
            if pat.search(line):
                findings.append({
                    "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "line": lineno,
                    "kind": kind,
                    "snippet": line.strip()[:160],
                })
    return findings


def main() -> int:
    all_findings: list[dict] = []
    template_count = 0
    for path in TEMPLATE_ROOT.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        template_count += 1
        all_findings.extend(scan_template(path))

    by_kind: dict[str, int] = {}
    for f in all_findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_by": "scripts/audit_no_placeholder.py",
                "templates_scanned": template_count,
                "finding_count": len(all_findings),
                "by_kind": by_kind,
                "findings": all_findings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"audit_no_placeholder: scanned {template_count} templates")
    print(f"  findings:    {len(all_findings)}")
    if by_kind:
        print(f"  histogram:")
        for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
            print(f"    {n:4d}  {k}")
    print(f"  written:     {OUT_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
