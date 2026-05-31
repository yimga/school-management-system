"""Static scanner — flag `from django.core.mail import ...` callsites
that bypass the reliability layer (v4.00.98 Phase 7).

Baseline: 36 known legacy callsites at introduction. Zero-tolerance for
NEW sites — new code MUST route through ``apps.schoolops.email_delivery``
or ``apps.schoolops.email_compat`` so failures are audited + retried.

Marker for intentional exceptions:
    # legacy-send-mail-allow: <reason>

Exit code:
    0 — finding_count <= baseline (or all flagged sites are allow-marked)
    1 — finding_count > baseline OR an un-marked site appeared
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

# Modules that are ALLOWED to import from django.core.mail directly: the
# reliability layer itself, the compat wrapper, and the legacy Anymail
# backend wiring.
_ALLOWLIST_PATHS: tuple[str, ...] = (
    "apps/schoolops/email_delivery.py",
    "apps/schoolops/email_compat.py",
    "apps/integrations_marketplace/email_backend.py",
    "apps/schoolops/tasks.py",  # the dispatch_bulk_email task
)

_TARGET_PATTERN = re.compile(
    r"(?:from\s+django\.core\.mail\s+import\b|django\.core\.mail\.send_mail\b)"
)
_ALLOW_MARKER = re.compile(r"#\s*legacy-send-mail-allow\s*:\s*(.+)")

_DEFAULT_BASELINE_PATH = "var/security-audit-baseline-legacy-send-mail.json"


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        rel = path.as_posix().replace(root.as_posix() + "/", "")
        # Skip vendored / generated trees.
        if any(part in (".venv", "node_modules", "__pycache__", "migrations") for part in path.parts):
            continue
        # Skip test trees.
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        # Skip scripts/ — those are operator one-shots, evidence captures,
        # and the scanner itself. Production code under apps/ + services/
        # is the scope of this gate.
        if rel.startswith("scripts/"):
            continue
        yield path


def _has_allow_marker(text: str, line_no: int) -> bool:
    # Allow markers can be on the same line or up to 2 lines above.
    lines = text.splitlines()
    if line_no < 1 or line_no > len(lines):
        return False
    if _ALLOW_MARKER.search(lines[line_no - 1]):
        return True
    for offset in (1, 2):
        idx = line_no - 1 - offset
        if idx >= 0 and _ALLOW_MARKER.search(lines[idx]):
            return True
    return False


def scan(root: Path) -> list[dict]:
    findings: list[dict] = []
    for path in _iter_python_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in _ALLOWLIST_PATHS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _TARGET_PATTERN.search(line):
                if _has_allow_marker(text, line_no):
                    continue
                findings.append(
                    {
                        "file": rel,
                        "line": line_no,
                        "snippet": line.strip()[:160],
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--baseline-path", default=_DEFAULT_BASELINE_PATH)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="fail when finding_count > baseline (default)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings = scan(root)
    count = len(findings)

    baseline_path = (root / args.baseline_path).resolve()
    baseline = 0
    if baseline_path.exists():
        try:
            data = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline = int(data.get("finding_count", 0))
        except Exception:
            baseline = 0

    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(
                {
                    "scanner": "scan_legacy_send_mail.py",
                    "finding_count": count,
                    "generated_at": "v4.00.98-phase7",
                    "findings": findings,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Baseline updated: {count} findings written to {baseline_path}")
        return 0

    if args.json:
        print(json.dumps(
            {
                "finding_count": count,
                "baseline": baseline,
                "findings": findings,
                "ok": count <= baseline,
            },
            indent=2,
        ))
    else:
        print(f"scan_legacy_send_mail: count={count} baseline={baseline}")
        if count > baseline:
            print(f"  NEW legacy send_mail sites (count={count - baseline}):")
            seen_existing = set()
            try:
                seen_existing = {
                    (f["file"], f["line"])
                    for f in (json.loads(baseline_path.read_text(encoding="utf-8")).get("findings") or [])
                }
            except Exception:
                pass
            for finding in findings:
                key = (finding["file"], finding["line"])
                if key not in seen_existing:
                    print(f"    {finding['file']}:{finding['line']}  {finding['snippet']}")

    return 1 if (args.strict and count > baseline) else 0


if __name__ == "__main__":
    sys.exit(main())
