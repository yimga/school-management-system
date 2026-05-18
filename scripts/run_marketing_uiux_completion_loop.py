#!/usr/bin/env python3
"""
Resumable RunMyCampus marketing UI/UX completion loop.

The loop has two jobs:
- Assert the current marketing shell contains the elite footer/UI primitives for this wave.
- Run the existing repo gates that protect templates, theme attributes, CSS visibility, and service-worker freshness.

If a gate fails, the script records the failed gate in ``var/marketing-uiux-loop-state.json``.
The next run resumes from that gate unless ``--restart`` is supplied.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "var" / "marketing-uiux-loop-state.json"
REPORT_PATH = ROOT / "docs" / "generated" / "marketing_uiux_completion_loop.json"


@dataclass(frozen=True)
class Gate:
    key: str
    label: str
    command: tuple[str, ...] | None = None


@dataclass
class GateResult:
    key: str
    label: str
    status: str
    returncode: int
    started_at: str
    finished_at: str


REQUIRED_SNIPPETS = {
    "templates/marketing/marketing_footer.html": (
        "mkt-footer-command",
        "mkt-footer-intelligence",
        "mkt-footer-proof-grid",
        "mkt-footer-route-stack",
        "data-mkt-theme-choice=\"system\"",
    ),
    "templates/marketing/marketing_header.html": (
        'href="{% url \'find_school\' %}"',
        'href="{% url \'status\' %}"',
    ),
    "templates/marketing/find_campus.html": (
        "data-rmc-os-find-campus",
        "find-campus-results",
    ),
    "templates/marketing/public_status.html": (
        "data-rmc-os-status-page",
        "rmc-os-component",
    ),
    "templates/marketing/partials/trust_compliance_anchors.html": (
        'id="ferpa"',
        'id="coppa"',
        'id="accessibility"',
        'id="security-matrix"',
        'id="infrastructure"',
    ),
    "static/css/rmc-corporate-os.css": (
        "--rmc-os-bg-canvas",
        "--rmc-os-surface-glass",
        "--rmc-os-ease-decelerate",
        "data-rmc-density",
    ),
    "static/marketing/css/marketing-shell.css": (
        "--mkt-elite-ease",
        "--mkt-elite-surface-glass",
        ".mkt-footer-intelligence",
        ".mkt-footer-proof-grid",
        "@media (prefers-reduced-motion: reduce)",
    ),
    "static/marketing/css/marketing-corporate-os.css": (
        ".rmc-os-hero",
        ".rmc-os-route-card",
        ".mkt-corporate-os-chrome",
    ),
    "static/marketing/js/theme-toggle.js": (
        "data-theme-preference",
        "systemTheme",
        "RunMyCampusMarketingTheme",
    ),
    "static/marketing/js/marketing-corporate-os.js": (
        "data-rmc-density-choice",
        "refreshStatusPill",
    ),
    "apps/observability/public_status.py": (
        "build_public_status_payload",
        "public_status",
    ),
}


def _py() -> str:
    return sys.executable


GATES: tuple[Gate, ...] = (
    Gate("contract", "Marketing footer/UI primitive contract"),
    Gate(
        "template-safety",
        "Template render safety",
        (_py(), "scripts/audit_template_render_safety.py", "--strict"),
    ),
    Gate(
        "theme-attribute-contract",
        "Theme attribute contract",
        (_py(), "scripts/scan_theme_attribute_contract.py", "--strict"),
    ),
    Gate(
        "reveal-invariants",
        "Reveal armed invariants",
        (_py(), "scripts/scan_reveal_armed_invariants.py", "--strict"),
    ),
    Gate(
        "sticky-overflow",
        "Sticky overflow safety",
        (_py(), "scripts/scan_sticky_with_overflow_hidden.py", "--strict"),
    ),
    Gate(
        "off-token-colors",
        "Off-token color safety",
        (_py(), "scripts/scan_off_token_colors.py", "--strict"),
    ),
    Gate(
        "theme-locked-tokens",
        "Theme-locked token safety",
        (_py(), "scripts/scan_theme_locked_token_text.py", "--strict"),
    ),
    Gate(
        "marketing-urls",
        "Marketing URL smoke",
        (_py(), "manage.py", "validate_marketing_urls", "--smoke"),
    ),
    Gate(
        "corporate-os-tests",
        "Corporate OS public surface tests",
        (
            _py(),
            "manage.py",
            "test",
            "apps.schools.tests.test_corporate_os_public_surfaces",
            "--verbosity=1",
            "--no-input",
        ),
    ),
    Gate(
        "service-worker",
        "Service worker cache-version gate",
        (_py(), "scripts/verify_service_worker_version.py", "--check-monotonic"),
    ),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-passes", type=int, default=3, help="Maximum loop passes before exiting on failure.")
    parser.add_argument("--restart", action="store_true", help="Ignore saved state and start from the first gate.")
    parser.add_argument("--list-gates", action="store_true", help="Print the ordered gate list and exit.")
    return parser.parse_args(argv)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_next_gate_index(restart: bool) -> int:
    if restart or not STATE_PATH.exists():
        return 0
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    key = payload.get("next_gate")
    for index, gate in enumerate(GATES):
        if gate.key == key:
            return index
    return 0


def _write_state(next_gate: Gate | None, results: list[GateResult]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _iso_now(),
        "status": "complete" if next_gate is None else "blocked",
        "next_gate": None if next_gate is None else next_gate.key,
        "results": [asdict(result) for result in results],
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    STATE_PATH.write_text(text, encoding="utf-8")
    REPORT_PATH.write_text(text, encoding="utf-8")


def _run_contract() -> tuple[int, str]:
    failures: list[str] = []
    for relpath, snippets in REQUIRED_SNIPPETS.items():
        path = ROOT / relpath
        if not path.is_file():
            failures.append(f"{relpath}: missing file")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for snippet in snippets:
            if snippet not in text:
                failures.append(f"{relpath}: missing {snippet!r}")
    if failures:
        return 1, "\n".join(failures)
    return 0, "Marketing UI/UX contract satisfied."


def _run_gate(gate: Gate) -> GateResult:
    started = _iso_now()
    print(f"--- {gate.label} ---", flush=True)
    if gate.command is None:
        returncode, output = _run_contract()
        if output:
            print(output, flush=True)
    else:
        proc = subprocess.run(gate.command, cwd=ROOT, shell=False)
        returncode = proc.returncode
    status = "passed" if returncode == 0 else "failed"
    print(f"{status.upper()}: {gate.label}\n", flush=True)
    return GateResult(
        key=gate.key,
        label=gate.label,
        status=status,
        returncode=returncode,
        started_at=started,
        finished_at=_iso_now(),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_passes < 1:
        print("--max-passes must be >= 1", file=sys.stderr)
        return 2
    if args.list_gates:
        for index, gate in enumerate(GATES, start=1):
            print(f"{index}. {gate.key}: {gate.label}")
        return 0

    start_index = _load_next_gate_index(args.restart)
    results: list[GateResult] = []
    for pass_number in range(1, args.max_passes + 1):
        print(f"=== Marketing UI/UX completion pass {pass_number}/{args.max_passes} ===", flush=True)
        for gate in GATES[start_index:]:
            result = _run_gate(gate)
            results.append(result)
            if result.returncode != 0:
                _write_state(gate, results)
                start_index = GATES.index(gate)
                break
        else:
            _write_state(None, results)
            print("Marketing UI/UX completion loop is green.", flush=True)
            return 0

    failed_key = results[-1].key if results else GATES[start_index].key
    print(
        f"Marketing UI/UX completion loop stopped at {failed_key}. "
        f"Fix that gate, then rerun this script to resume.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
