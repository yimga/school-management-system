#!/usr/bin/env python3
"""v4.00.91 — assist_dock off-registry usage scanner.

Catches code that adds chips to the assist dock without going through the
``apps.assist_dock.registry`` SOT. Specifically:

  * Direct ``document.querySelector(".ai-copilot-wrapper")`` / ``.voc-widget``
    / ``.cp-context-drawer-toggle`` / ``[data-rmc-page-help]`` / ``.portal-chathead``
    / ``#back-to-top-btn`` calls in NEW JS files (the canonical
    ``rmc-assist-dock.js`` is the only legitimate adopter — every other
    consumer should target ``[data-rmc-assist-slot-id="<id>"]``).
  * Direct DOM-injection into ``.rmc-assist-dock`` / ``[data-rmc-assist-dock]``
    in any JS file outside ``rmc-assist-dock.js`` (write-through means the
    registry no longer reflects the rendered chips).

Honors per-line ``// assist-dock-offregistry-allow: <reason>`` markers for
intentional exceptions (e.g. defensive cleanup during shell teardown).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BASELINE = ROOT / "var" / "security-audit-baseline-assist-dock-offregistry.json"
ALLOW_MARKER = "assist-dock-offregistry-allow:"

# JS files that ARE the canonical adopter — allowed.
# Widget-owner files are also allowed: a widget querying its own root by its
# canonical CSS class is the source of truth — the dock adopts it, not the
# other way around. Adding a chip = registry entry, not editing this list.
LEGITIMATE_ADOPTERS = frozenset(
    {
        "static/js/rmc-assist-dock.js",
        # AI copilot widget's own init — owns `.ai-copilot-wrapper`.
        "static/js/_pages/components__ai_copilot-1.js",
    }
)

# Selectors that historically targeted dock source nodes. Off-registry use
# in new JS is a smell — those nodes are owned by the registry now.
LEGACY_SOURCE_SELECTORS = (
    ".ai-copilot-wrapper",
    ".voc-widget",
    ".cp-context-drawer-toggle",
    "[data-rmc-page-help]",
    ".portal-chathead",
    "#back-to-top-btn",
    "#aiCopilotTrigger",
    "#aiCopilotPanel",
)

DOCK_CHROME_SELECTORS = (
    ".rmc-assist-dock",
    "[data-rmc-assist-dock]",
)

JS_DIRS = (
    "static/js",
    "static/js/_pages",
    "tests/js",
)


_QUERYSELECTOR_PATTERN = re.compile(
    r"document\.querySelector(?:All)?\s*\(\s*[\"']([^\"']+)[\"']\s*\)"
)
_INSERT_PATTERN = re.compile(
    r"(?:innerHTML|appendChild|insertBefore|insertAdjacentHTML)\b"
)


def _is_legitimate(rel_path: str) -> bool:
    rel_norm = rel_path.replace("\\", "/")
    return rel_norm in LEGITIMATE_ADOPTERS


def _line_has_allow(line: str) -> bool:
    return ALLOW_MARKER in line


def _scan_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    rel = path.relative_to(ROOT).as_posix()
    if _is_legitimate(rel):
        return findings
    for i, line in enumerate(text.splitlines(), start=1):
        if _line_has_allow(line):
            continue
        for match in _QUERYSELECTOR_PATTERN.finditer(line):
            sel = match.group(1)
            if sel in LEGACY_SOURCE_SELECTORS:
                findings.append(
                    {
                        "file": rel,
                        "line": i,
                        "selector": sel,
                        "issue": "legacy dock source selector — adopt via [data-rmc-assist-slot-id] instead",
                    }
                )
            elif any(chrome in sel for chrome in DOCK_CHROME_SELECTORS) and _INSERT_PATTERN.search(line):
                findings.append(
                    {
                        "file": rel,
                        "line": i,
                        "selector": sel,
                        "issue": "direct DOM injection into dock chrome — register a slot instead",
                    }
                )
    return findings


def _walk_js() -> list[Path]:
    out: list[Path] = []
    for rel in JS_DIRS:
        base = ROOT / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*.js"):
            out.append(path)
        for path in base.rglob("*.ts"):
            out.append(path)
    return out


def _load_baseline() -> int:
    if not BASELINE.is_file():
        return 0
    try:
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if isinstance(data, dict):
        for key in ("finding_count", "total"):
            value = data.get(key)
            if isinstance(value, int):
                return value
    return 0


def _write_baseline(findings: list[dict]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "finding_count": len(findings),
        "findings": findings,
        "generated_by": "scan_assist_dock_offregistry.py",
    }
    BASELINE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="assist_dock off-registry usage scanner")
    parser.add_argument("--strict", action="store_true", help="fail on any finding")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings: list[dict] = []
    for path in _walk_js():
        findings.extend(_scan_file(path))

    if args.update_baseline:
        _write_baseline(findings)
        print(f"Updated baseline: {len(findings)} finding(s)")
        return 0

    if args.json:
        json.dump({"finding_count": len(findings), "findings": findings}, sys.stdout, indent=2)
        sys.stdout.write("\n")

    baseline_count = _load_baseline()
    if args.strict and findings:
        if not args.json:
            for f in findings:
                print(f"FAIL: {f}", file=sys.stderr)
        print(f"FAIL: {len(findings)} finding(s); strict baseline=0", file=sys.stderr)
        return 1
    if len(findings) > baseline_count:
        if not args.json:
            for f in findings:
                print(f"FAIL: {f}", file=sys.stderr)
        print(
            f"FAIL: {len(findings)} findings > baseline {baseline_count}", file=sys.stderr
        )
        return 1
    if not args.json:
        print(f"OK: {len(findings)} finding(s); baseline={baseline_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
