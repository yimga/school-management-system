#!/usr/bin/env python3
"""Executable gate for the local marketing redesign execution prompt contract.

This validates the prompt document itself. It does not certify the Phase 0-4
marketing implementation; those product gates are listed inside the prompt and
must be run during the implementation phases.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT = Path.home() / ".claude" / "plans" / "i-want-you-to-twinkly-spark.md"
GENERATED_JSON = ROOT / "docs" / "generated" / "marketing_redesign_prompt_contract_audit.json"
GENERATED_MD = ROOT / "docs" / "generated" / "marketing_redesign_prompt_contract_audit.md"


@dataclass
class Row:
    check_id: str
    category: str
    description: str
    status: str
    proof: str


REQUIRED_SECTIONS = (
    "## Execution operating contract",
    "### Prompt completeness audit",
    "### Prompt self-check gates",
    "### Repository scope",
    "### Source-of-truth precedence",
    "### Non-negotiable implementation rules",
    "### Deliverables per phase",
    "### Implementation definition of done",
    "### Canonical route, template, and slug matrix",
    "## Component inventory",
    "## Critical files",
    "### Phase 0",
    "### Phase 1",
    "### Phase 2",
    "### Phase 3",
    "### Phase 4",
    "## Verification",
    "## Final sign-off protocol",
    "### Completion scoring rubric",
    "### Stop condition",
)

CANONICAL_ROUTES = (
    "/run/admissions/",
    "/run/attendance/",
    "/run/analytics/",
    "/teach/gradebook/",
    "/pay/fees-payments/",
    "/communicate/messages/",
    "/communicate/portals/",
    "/grow/marketplace/",
)

REQUIRED_REPO_FILES = (
    "static/js/rmc-reveal.js",
    "scripts/audit_route_surface.py",
    "scripts/verify_i18n_catalog_fresh.py",
    "scripts/check_marketing_assets_claimed_vs_present.py",
    "scripts/scan_undefined_css_classes.py",
    "scripts/scan_inline_style_off_token.py",
    "scripts/scan_bell_clock_consistency.py",
    "scripts/check_documented_baselines.py",
    "apps/schools/management/commands/validate_marketing_urls.py",
    "apps/schools/tests/test_marketing_nav_contract.py",
    "apps/schools/tests/test_marketing_validation.py",
    "apps/schools/tests/test_marketing_product_page_phase_h.py",
    "apps/schools/tests/test_marketing_page_management.py",
    "apps/schools/tests/test_marketing_phase0_visual_truth.py",
    "apps/schools/tests/test_marketing_phase1_foundation.py",
)

BANNED_PATTERNS = (
    (r"TODO", "TODO marker"),
    (r"TBD", "TBD marker"),
    (r"\[PASTE\]", "paste placeholder"),
    (r"placeholder", "placeholder wording"),
    (r"\bstub\b", "stub wording"),
    (r"\bmaybe\b", "maybe wording"),
    (r"\boptional\b", "optional wording"),
    (r"\bpreferred\b", "preferred wording"),
    (r"when ready", "when-ready wording"),
    (r"follow-up", "follow-up wording"),
    (r"apps\.marketing", "nonexistent apps.marketing test path"),
    (r"type_platform_detail", "stale type_platform_detail template reference"),
    (r"static/marketing/js/rmc-reveal\.js", "stale rmc-reveal path"),
    (r"8KB total new JS", "conflicting old JS budget"),
    (r"50\+", "unbounded 50+ wording"),
    (r"per memory", "memory-based claim source"),
    (r"\bapprox\b", "approx wording"),
    (r"\baround\b", "around wording"),
    (r"~", "tilde approximation marker"),
)

REQUIRED_EXACT_STRINGS = (
    "Primary repository root: `beta/school-management-system`",
    "Source-of-truth precedence",
    "marketing_inner_default.html` no longer routed except as fallback",
    "No top-nav page is visually or structurally dependent on the generic inner-page template.",
    "A score below 100 blocks sign-off.",
    "Stop only after all ship gates pass, the scoring rubric is 100/100",
    "templates/marketing/pages/platform_detail.html",
    "static/js/rmc-reveal.js",
    "python scripts/check_marketing_assets_claimed_vs_present.py",
    "python scripts/scan_undefined_css_classes.py",
    "python scripts/scan_inline_style_off_token.py",
    "python scripts/scan_bell_clock_consistency.py",
    "python scripts/check_documented_baselines.py",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _add(rows: list[Row], check_id: str, category: str, description: str, ok: bool, proof: str) -> None:
    rows.append(
        Row(
            check_id=check_id,
            category=category,
            description=description,
            status="PASS" if ok else "FAIL",
            proof=proof,
        )
    )


def _matching_lines(text: str, pattern: str) -> list[str]:
    rx = re.compile(pattern, re.IGNORECASE)
    matches: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if rx.search(line):
            matches.append(f"L{number}: {line.strip()}")
    return matches


def _build_rows(prompt_path: Path) -> list[Row]:
    rows: list[Row] = []

    if not prompt_path.is_file():
        _add(
            rows,
            "prompt.exists",
            "prompt",
            "Local execution prompt exists",
            False,
            str(prompt_path),
        )
        return rows

    text = _read(prompt_path)
    _add(
        rows,
        "prompt.exists",
        "prompt",
        "Local execution prompt exists",
        True,
        str(prompt_path),
    )

    missing_sections = [section for section in REQUIRED_SECTIONS if section not in text]
    _add(
        rows,
        "structure.required_sections",
        "structure",
        "All required contract sections are present",
        not missing_sections,
        "all required sections present" if not missing_sections else "; ".join(missing_sections),
    )

    phase_count = len(re.findall(r"^### Phase [0-4]\b", text, flags=re.MULTILINE))
    ship_gate_count = len(re.findall(r"\*\*Ship gate", text))
    _add(
        rows,
        "structure.phase_gates",
        "structure",
        "Exactly five phases and five ship gates are present",
        phase_count == 5 and ship_gate_count == 5,
        f"phases={phase_count}; ship_gates={ship_gate_count}",
    )

    missing_routes = [route for route in CANONICAL_ROUTES if route not in text]
    _add(
        rows,
        "routes.canonical_modules",
        "routes",
        "All eight canonical module routes are specified",
        not missing_routes,
        "all canonical module routes present" if not missing_routes else "; ".join(missing_routes),
    )

    missing_strings = [value for value in REQUIRED_EXACT_STRINGS if value not in text]
    _add(
        rows,
        "contract.exact_requirements",
        "contract",
        "Critical exact requirements are present",
        not missing_strings,
        "all critical exact requirements present" if not missing_strings else "; ".join(missing_strings),
    )

    banned_hits: list[str] = []
    for pattern, label in BANNED_PATTERNS:
        for match in _matching_lines(text, pattern):
            banned_hits.append(f"{label}: {match}")
    _add(
        rows,
        "language.no_ambiguous_patterns",
        "language",
        "No unresolved placeholder, ambiguity, or stale-command patterns remain",
        not banned_hits,
        "no banned patterns found" if not banned_hits else " | ".join(banned_hits[:20]),
    )

    score_numbers = [int(value) for value in re.findall(r"\|\s*(\d+)\s*\|", text)]
    rubric_total = sum(score_numbers[-8:]) if len(score_numbers) >= 8 else 0
    _add(
        rows,
        "signoff.rubric",
        "signoff",
        "Final scoring rubric totals 100 points and blocks below 100",
        rubric_total == 100 and "A score below 100 blocks sign-off." in text and "100/100" in text,
        f"rubric_total={rubric_total}; has_100_stop={'100/100' in text}",
    )

    missing_files = [rel for rel in REQUIRED_REPO_FILES if not (ROOT / rel).is_file()]
    _add(
        rows,
        "repo.validation_targets",
        "repo",
        "Repo-backed scanner and test targets named by the prompt exist",
        not missing_files,
        "all repo-backed targets exist" if not missing_files else "; ".join(missing_files),
    )

    sot = ROOT / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
    sot_text = _read(sot) if sot.is_file() else ""
    sot_ok = (
        "MARKETING REDESIGN PROMPT CONTRACT REVALIDATED - 100% PROMPT COMPLETE" in sot_text
        and "prompt contract only" in sot_text
    )
    _add(
        rows,
        "sot.revalidation_note",
        "sot",
        "SOT records the prompt-complete revalidation boundary",
        sot_ok,
        "SOT prompt-complete note present" if sot_ok else "SOT prompt-complete note missing",
    )

    return rows


def _write_artifacts(prompt_path: Path, rows: list[Row]) -> None:
    GENERATED_JSON.parent.mkdir(parents=True, exist_ok=True)
    failures = [row for row in rows if row.status != "PASS"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_path": str(prompt_path),
        "status": "PASS" if not failures else "FAIL",
        "summary": {
            "total": len(rows),
            "passed": len(rows) - len(failures),
            "failed": len(failures),
        },
        "rows": [asdict(row) for row in rows],
    }
    GENERATED_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Marketing Redesign Prompt Contract Audit",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Prompt: `{prompt_path}`",
        f"- Status: **{payload['status']}**",
        f"- Checks: **{payload['summary']['passed']} / {payload['summary']['total']} PASS**",
        "",
        "| Check | Category | Status | Proof |",
        "|---|---|---|---|",
    ]
    for row in rows:
        proof = row.proof.replace("|", "\\|")
        lines.append(f"| `{row.check_id}` | {row.category} | **{row.status}** | {proof} |")
    GENERATED_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default=str(DEFAULT_PROMPT),
        help="Path to the marketing redesign execution prompt.",
    )
    parser.add_argument("--write", action="store_true", help="Write docs/generated audit artifacts.")
    args = parser.parse_args(argv)

    prompt_path = Path(args.prompt).expanduser().resolve()
    rows = _build_rows(prompt_path)
    if args.write:
        _write_artifacts(prompt_path, rows)

    failures = [row for row in rows if row.status != "PASS"]
    if failures:
        print("verify_marketing_redesign_prompt_contract: FAIL", file=sys.stderr)
        for row in failures:
            print(f"  - {row.check_id}: {row.proof}", file=sys.stderr)
        return 1

    print("verify_marketing_redesign_prompt_contract: PASS (prompt contract 100% complete)")
    if args.write:
        print(f"  wrote {GENERATED_JSON.relative_to(ROOT)}")
        print(f"  wrote {GENERATED_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
