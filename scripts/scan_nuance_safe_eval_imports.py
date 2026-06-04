"""Scan: production code must not import nuance_engine._safe_eval (use evaluate_json_logic)."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_ROOTS = (REPO_ROOT / "apps", REPO_ROOT / "services")
ALLOWED_FILE = REPO_ROOT / "apps" / "siteconfig" / "nuance_engine.py"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-nuance-safe-eval-imports.json"
ALLOW_MARKER = "nuance-safe-eval-import-allow:"
IMPORT_RE = re.compile(
    r"(?:from\s+apps\.siteconfig\.nuance_engine\s+import\s+.*\b_safe_eval\b"
    r"|from\s+\.nuance_engine\s+import\s+.*\b_safe_eval\b"
    r"|import\s+apps\.siteconfig\.nuance_engine\s+.*\b_safe_eval\b)"
)


def _scan_file(path: pathlib.Path) -> list[dict]:
    if path == ALLOWED_FILE:
        return []
    rel = path.relative_to(REPO_ROOT).as_posix()
    if "/tests/" in rel or rel.endswith("_test.py") or "/test_" in rel:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    findings: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        if IMPORT_RE.search(line) or "_safe_eval" in line and "import" in line:
            if "_safe_eval" in line:
                findings.append(
                    {"file": rel, "line": line_no, "snippet": line.strip()[:120]}
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    all_findings: list[dict] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            all_findings.extend(_scan_file(path))

    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(
                {"finding_count": len(all_findings), "findings": all_findings},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote baseline ({len(all_findings)} findings) to {BASELINE_PATH}")
        return 0

    baseline_count = 0
    if BASELINE_PATH.is_file():
        baseline_count = int(json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get("finding_count", 0))

    if args.json:
        print(json.dumps({"finding_count": len(all_findings), "findings": all_findings}, indent=2))
    elif all_findings:
        for f in all_findings:
            print(f"{f['file']}:{f['line']}: {f['snippet']}")

    if args.strict and len(all_findings) != baseline_count:
        print(
            f"scan_nuance_safe_eval_imports: {len(all_findings)} findings "
            f"(baseline {baseline_count})",
            file=sys.stderr,
        )
        return 1
    if args.strict and len(all_findings) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
