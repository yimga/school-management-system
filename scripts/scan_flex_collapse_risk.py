"""Scan: descendant layout-row selectors that collapse nested content grids.

Shell sidebar+main rows should use direct-child combinators (`.cp-layout > .row`,
`.portal-layout-row`). Descendant selectors (`.cp-layout .row`) also match Bootstrap
`.row` inside `#cp-main-content`, forcing nowrap and squashing module cards.

Mark intentional sites with `flex-collapse-risk-allow: <reason>` in the rule body.

Usage:
    python scripts/scan_flex_collapse_risk.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS_DIRS = [
    REPO_ROOT / "static" / "css",
    REPO_ROOT / "static" / "marketing" / "css",
]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-flex-collapse-risk.json"

ALLOW_MARKER = "flex-collapse-risk-allow:"
RISK_PATTERNS = (
    re.compile(r"\.cp-layout\s+\.row\b"),
    re.compile(r"\.portal-layout-wrap\s+\.row\b"),
    re.compile(r"#cp-main-content\s+\.row\b[^,{]*\{[^}]*flex-wrap\s*:\s*nowrap"),
)


def _strip_comments(text: str) -> str:
    return re.sub(
        r"/\*(?!.*" + re.escape(ALLOW_MARKER) + r").*?\*/",
        "",
        text,
        flags=re.DOTALL,
    )


def scan_file(path: pathlib.Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    stripped = _strip_comments(raw)
    findings: list[dict] = []

    for pattern in RISK_PATTERNS[:2]:
        for match in pattern.finditer(raw):
            line = raw.count("\n", 0, match.start()) + 1
            context_start = max(0, match.start() - 160)
            context_end = min(len(raw), match.end() + 160)
            context = raw[context_start:context_end].replace("\n", " ").strip()
            if ALLOW_MARKER in context:
                continue
            findings.append(
                {
                    "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "line": line,
                    "selector_fragment": match.group(0),
                    "context": context[:240],
                }
            )

    for match in RISK_PATTERNS[2].finditer(stripped):
        line = stripped.count("\n", 0, match.start()) + 1
        context = match.group(0).replace("\n", " ").strip()[:240]
        if ALLOW_MARKER in context:
            continue
        findings.append(
            {
                "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "line": line,
                "selector_fragment": "#cp-main-content .row { flex-wrap: nowrap",
                "context": context,
            }
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings: list[dict] = []
    for css_dir in CSS_DIRS:
        if not css_dir.is_dir():
            continue
        for path in sorted(css_dir.rglob("*.css")):
            findings.extend(scan_file(path))

    payload = {
        "finding_count": len(findings),
        "findings": findings,
    }

    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline: {BASELINE_PATH} ({len(findings)} findings)")
        return 0

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for item in findings:
            print(f"{item['file']}:{item['line']}: {item['selector_fragment']}")
        print(f"flex-collapse-risk findings: {len(findings)}")

    if args.strict and findings:
        return 1

    if BASELINE_PATH.is_file():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        if baseline.get("finding_count", 0) != len(findings):
            print(
                f"Baseline drift: recorded {baseline.get('finding_count')} vs current {len(findings)}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
