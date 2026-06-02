"""Scan: SIGALRM / ITIMER_REAL must not be used outside nuance_engine's guarded path.

Gunicorn ``gthread`` workers are not the main interpreter thread; ``signal.signal(SIGALRM)``
raises ``ValueError: signal only works in main thread``.

Allowed: ``apps/siteconfig/nuance_engine.py`` only (inside ``_run_with_timeout`` behind
``_sigalrm_timeout_available()``).

Mark rare intentional sites with ``# sigalrm-worker-thread-allow: <reason>`` on the same line.

Usage:
    python scripts/scan_sigalrm_worker_thread_safety.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_ROOTS = (REPO_ROOT / "apps", REPO_ROOT / "services")
ALLOWED_FILE = REPO_ROOT / "apps" / "siteconfig" / "nuance_engine.py"
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-sigalrm-worker-thread-safety.json"
)
ALLOW_MARKER = "sigalrm-worker-thread-allow:"
PATTERNS = (
    re.compile(r"\bsignal\.SIGALRM\b"),
    re.compile(r"\bsignal\.setitimer\s*\("),
    re.compile(r"\bsignal\.ITIMER_REAL\b"),
    re.compile(r"\bsignal\.alarm\s*\("),
)


def _scan_file(path: pathlib.Path) -> list[dict]:
    if path == ALLOWED_FILE:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    findings: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for pattern in PATTERNS:
            if pattern.search(line):
                findings.append(
                    {
                        "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "line": line_no,
                        "pattern": pattern.pattern,
                        "snippet": line.strip()[:120],
                    }
                )
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings: list[dict] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "/migrations/" in path.as_posix() or "/tests/" in path.as_posix():
                continue
            findings.extend(_scan_file(path))

    payload = {
        "finding_count": len(findings),
        "findings": findings,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    elif findings:
        for item in findings:
            print(f"{item['file']}:{item['line']}: {item['snippet']}")

    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline {BASELINE_PATH} ({len(findings)} findings)")
        return 0

    if args.strict:
        baseline_count = 0
        if BASELINE_PATH.is_file():
            baseline_count = int(
                json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get(
                    "finding_count", 0
                )
            )
        if len(findings) > baseline_count:
            print(
                f"FAIL: {len(findings)} SIGALRM/itimer sites (baseline {baseline_count})",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
