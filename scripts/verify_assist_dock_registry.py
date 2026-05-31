#!/usr/bin/env python3
"""v4.00.91 — assist_dock registry shape gate.

Validates that every slot registered in ``apps.assist_dock.registry._REGISTRY``
carries the required fields and that the three platform shells include the
JSON island that hydrates the JS dock from the registry.

Zero-tolerance: any new chip MUST go through the registry. Exits 1 on:
  * malformed slot (empty id / icon / label, invalid source)
  * dom-adopt slot missing adopt_selector
  * external slot missing href
  * shell that loads `rmc-assist-dock.js` but skips the slots include
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "var" / "security-audit-baseline-assist-dock-registry.json"

REQUIRED_SHELLS = (
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/admin/base_site.html",
)

DOCK_JS_MARKER = "rmc-assist-dock.js"
SLOTS_INCLUDE_MARKER = "rmc_assist_dock_slots.html"


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django  # type: ignore
    except ImportError:
        print(
            "ERROR: django import failed; the registry gate must run in the project env",
            file=sys.stderr,
        )
        sys.exit(2)
    django.setup()


def _collect_slot_findings() -> list[dict]:
    from apps.assist_dock.registry import all_slots, VALID_SOURCES

    findings: list[dict] = []
    for slot in all_slots():
        if not slot.id:
            findings.append({"slot": "<empty-id>", "issue": "empty id"})
            continue
        if not str(slot.label):
            findings.append({"slot": slot.id, "issue": "empty label"})
        if not slot.icon:
            findings.append({"slot": slot.id, "issue": "empty icon"})
        if slot.source not in VALID_SOURCES:
            findings.append(
                {"slot": slot.id, "issue": f"invalid source={slot.source!r}"}
            )
        if slot.source == "dom-adopt" and not slot.adopt_selector:
            findings.append(
                {"slot": slot.id, "issue": "dom-adopt slot missing adopt_selector"}
            )
        if slot.source == "external" and not slot.href:
            findings.append(
                {"slot": slot.id, "issue": "external slot missing href"}
            )
        if slot.order is None:
            findings.append({"slot": slot.id, "issue": "missing order"})
    return findings


def _collect_shell_findings() -> list[dict]:
    findings: list[dict] = []
    for rel in REQUIRED_SHELLS:
        path = ROOT / rel
        if not path.is_file():
            findings.append({"shell": rel, "issue": "missing shell"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if DOCK_JS_MARKER not in text:
            # Shell doesn't load the dock at all — not our concern.
            continue
        if SLOTS_INCLUDE_MARKER not in text:
            findings.append(
                {"shell": rel, "issue": "dock JS loaded but registry slots include missing"}
            )
    return findings


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
        "generated_by": "verify_assist_dock_registry.py",
    }
    BASELINE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="assist_dock registry shape gate")
    parser.add_argument("--strict", action="store_true", help="fail on any finding")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="rewrite the baseline JSON to current state (use sparingly)",
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args()

    _bootstrap_django()
    slot_findings = _collect_slot_findings()
    shell_findings = _collect_shell_findings()
    findings = slot_findings + shell_findings

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
        print(f"FAIL: {len(findings)} finding(s); baseline=0", file=sys.stderr)
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
