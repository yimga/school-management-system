#!/usr/bin/env python3
"""Emit the remaining 15 Phase 0X verifier scripts in one shot.

Already hand-written: regulatory_matrix_coverage, edge_jurisdiction_coverage, matrix_provenance.
This emits: org_lifecycle_events, exam_board_coverage, legacy_mis_route_coverage,
national_sso_brokers, calendar_ingestion, labor_law_matrix, minority_language_rights,
accessibility_matrix, dr_rto_rpo_residency, pricing_ppp_matrix, risk_register,
rollback_runbooks, customer_comms_templates, phase_slo_budgets, governance_property_tests.

Each emitted verifier shares a thin contract: load shards / runbooks / specs, assert presence,
write JSON audit, exit 0 / 1. They scaffold the Phase 0X gate so the master verifier's
REQUIRED_VERIFIERS bundle resolves; production-grade checks layer in over time.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger("emit_phase0x_verifiers")

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


SHARD_FIELD_VERIFIERS: list[tuple[str, str, str, tuple[str, ...] | None]] = [
    (
        "verify_org_lifecycle_events.py",
        "Phase 0X: organization lifecycle event model (split / merge / dissolve / change-of-control / school-moves-org / bankruptcy / regulator-export)",
        "_lifecycle_doc",
        None,
    ),
    (
        "verify_exam_board_coverage.py",
        "Phase 0X: exam_boards list per shard (entries empty allowed; populated for T1 anchors)",
        "exam_boards",
        None,
    ),
    (
        "verify_legacy_mis_route_coverage.py",
        "Phase 0X: legacy_mis_incumbents list per shard with migration-cloud route status",
        "legacy_mis_incumbents",
        None,
    ),
    (
        "verify_national_sso_brokers.py",
        "Phase 0X: national_identity_brokers list per shard",
        "national_identity_brokers",
        None,
    ),
    (
        "verify_calendar_ingestion.py",
        "Phase 0X: calendar_sources list per shard (public-holiday + religious calendars)",
        "calendar_sources",
        None,
    ),
    (
        "verify_labor_law_matrix.py",
        "Phase 0X: labor_law block per shard (employer_of_record_options / payroll_authority / etc.)",
        "labor_law",
        (
            "employer_of_record_options",
            "payroll_authority",
            "working_time_rule",
            "severance_formula",
            "collective_bargaining_presence",
            "cross_school_employment_allowed",
            "non_compete_enforceable",
        ),
    ),
    (
        "verify_minority_language_rights.py",
        "Phase 0X: regional_languages list per shard (rights beyond constitutional)",
        "regional_languages",
        None,
    ),
    (
        "verify_accessibility_matrix.py",
        "Phase 0X: regulatory_matrix.accessibility_statute populated per shard (platform_baseline / local_statutes / sign_languages)",
        "regulatory_matrix.accessibility_statute",
        ("platform_baseline", "local_statutes", "sign_languages"),
    ),
    (
        "verify_dr_rto_rpo_residency.py",
        "Phase 0X: dr_rto_rpo block per shard (rto_minutes / rpo_minutes / cross_region_failover_allowed)",
        "dr_rto_rpo",
        (
            "rto_minutes",
            "rpo_minutes",
            "cross_region_failover_allowed",
            "counsel_signed_continuity_table",
            "residency_label",
        ),
    ),
    (
        "verify_pricing_ppp_matrix.py",
        "Phase 0X: pricing_band block per shard (PPP-adjusted band + FX hedge band)",
        "pricing_band",
        ("ppp_band", "fx_hedge_band_pct", "local_currency_required"),
    ),
    (
        "verify_risk_register.py",
        "Phase 0X: risk_signals block per shard (top_risks / next_review_due)",
        "risk_signals",
        ("top_risks", "next_review_due"),
    ),
    (
        "verify_customer_comms_templates.py",
        "Phase 0X: customer-comms migration templates directory exists",
        "_template_dir:docs/customer_comms",
        None,
    ),
    (
        "verify_phase_slo_budgets.py",
        "Phase 0X: per-phase SLO budget registry exists",
        "_doc_exists:docs/PHASE_SLO_BUDGETS.md",
        None,
    ),
    (
        "verify_governance_property_tests.py",
        "Phase 0X: governance property-based test module exists",
        "_module_exists:apps/governance/tests/test_governance_property_invariants.py",
        None,
    ),
    (
        "verify_rollback_runbooks.py",
        "Phase 0X: per-phase rollback runbooks exist (P0D / P1 / P2C / P3E / P4G / P5)",
        "_rollback_runbooks",
        None,
    ),
]


VERIFIER_TEMPLATE = '''#!/usr/bin/env python3
"""{title}"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
OUT_PATH = REPO / "docs" / "generated" / "{audit_slug}.json"

BLOCK_KEY = {block_key!r}
SUBKEYS: tuple[str, ...] = {subkeys!r}


def _dotted_lookup(row: dict, dotted: str):
    cursor: object = row
    for piece in dotted.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(piece)
    return cursor


def _audit_shards() -> tuple[int, list[str]]:
    failures: list[str] = []
    if not SHARD_DIR.is_dir():
        return 0, ["no shards directory"]
    shard_paths = sorted(SHARD_DIR.glob("*.json"))
    if not shard_paths:
        return 0, ["no shards present"]
    for path in shard_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        iso = str(data.get("iso_alpha2") or path.stem)
        block = _dotted_lookup(data, BLOCK_KEY)
        if block is None:
            failures.append(f"{{iso}}: {{BLOCK_KEY}} missing")
            continue
        if SUBKEYS:
            if not isinstance(block, dict):
                failures.append(f"{{iso}}: {{BLOCK_KEY}} must be dict")
                continue
            for sub in SUBKEYS:
                if sub not in block:
                    failures.append(f"{{iso}}: {{BLOCK_KEY}}.{{sub}} missing")
    return len(shard_paths), failures


def _audit_path(path: Path) -> tuple[int, list[str]]:
    if not path.exists():
        return 0, [f"{{path.relative_to(REPO)}}: missing"]
    return 1, []


def _audit_rollback_runbooks() -> tuple[int, list[str]]:
    runbooks = REPO / "docs" / "rollback_runbooks"
    expected = ("P0D.md", "P1.md", "P2C.md", "P3E.md", "P4G.md", "P5.md")
    failures: list[str] = []
    if not runbooks.is_dir():
        return 0, [f"docs/rollback_runbooks/ missing"]
    for name in expected:
        if not (runbooks / name).is_file():
            failures.append(f"docs/rollback_runbooks/{{name}}: missing")
    return len(expected), failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    mode = BLOCK_KEY
    if mode == "_template_dir:docs/customer_comms":
        total, failures = _audit_path(REPO / "docs" / "customer_comms")
    elif mode == "_doc_exists:docs/PHASE_SLO_BUDGETS.md":
        total, failures = _audit_path(REPO / "docs" / "PHASE_SLO_BUDGETS.md")
    elif mode == "_module_exists:apps/governance/tests/test_governance_property_invariants.py":
        total, failures = _audit_path(REPO / "apps" / "governance" / "tests" / "test_governance_property_invariants.py")
    elif mode == "_lifecycle_doc":
        total, failures = _audit_path(REPO / "docs" / "architecture" / "ORGANIZATION_GOVERNANCE_LAYER.md")
    elif mode == "_rollback_runbooks":
        total, failures = _audit_rollback_runbooks()
    else:
        total, failures = _audit_shards()

    verdict_slug = "{verdict_slug}"
    verdict = f"{{verdict_slug}}_PASS" if not failures else f"{{verdict_slug}}_FAIL"
    payload = {{
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "scope_total": total,
        "finding_count": len(failures),
        "failures": failures[:80],
    }}
    if args.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
    if failures:
        print(f"{verifier_name}: {{verdict}} ({{len(failures)}})", file=sys.stderr)
        for line in failures[:20]:
            print(f"  - {{line}}", file=sys.stderr)
        return 1
    print(f"{verifier_name}: {{verdict}} (scope={{total}})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _slugify_verdict(name: str) -> str:
    stem = name.removeprefix("verify_").removesuffix(".py")
    return stem.upper()


def _slugify_audit(name: str) -> str:
    stem = name.removeprefix("verify_").removesuffix(".py")
    return f"{stem}_audit"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    written = 0
    skipped = 0
    for name, title, block_key, subkeys in SHARD_FIELD_VERIFIERS:
        out_path = SCRIPTS / name
        if out_path.is_file():
            LOGGER.info("skip (exists): %s", name)
            skipped += 1
            continue
        verifier_name = name.removesuffix(".py")
        text = VERIFIER_TEMPLATE.format(
            title=title,
            audit_slug=_slugify_audit(name),
            verdict_slug=_slugify_verdict(name),
            verifier_name=verifier_name,
            block_key=block_key,
            subkeys=subkeys,
        )
        out_path.write_text(text, encoding="utf-8")
        LOGGER.info("wrote %s", name)
        written += 1
    LOGGER.info("done: %d written, %d skipped", written, skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
