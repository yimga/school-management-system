#!/usr/bin/env python3
"""Bootstrap global governance Phase 0A artifacts (register, matrix skeleton, ledger)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from lib.global_governance_geo import (  # noqa: E402
    continent_and_wave_for_alpha2,
    is_likely_territory,
    research_tier_for,
)

GENERATED = REPO / "docs" / "generated"
MATRIX_DIR = GENERATED / "country_governance_matrix"
REGISTER_PATH = GENERATED / "global_governance_completion_register.json"
MATRIX_PATH = GENERATED / "country_governance_matrix.json"
LEDGER_PATH = GENERATED / "country_dissection_ledger.json"

REGISTER_ITEMS: list[dict[str, Any]] = [
    {
        "id": "P0A-completion-register",
        "phase": "0A",
        "title": "Global governance completion register bootstrapped",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "docs/generated/global_governance_completion_register.json",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0A-aggressive-audit-loop",
        "phase": "0A",
        "title": "verify_global_governance_plan_completion.py master gate",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_governance_plan_completion.py --phase-max 0A",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0A-matrix-skeleton-249",
        "phase": "0A",
        "title": "country_governance_matrix.json skeleton — 249 ISO rows + shards",
        "agent_lane": "GEO",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_country_governance_matrix.py --allow-skeleton",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0A-dissection-ledger",
        "phase": "0A",
        "title": "country_dissection_ledger.json tracks all ISO codes",
        "agent_lane": "GEO",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_country_dissection_ledger.py --allow-skeleton",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0A-verifier-scaffold",
        "phase": "0A",
        "title": "Governance verifier scripts scaffolded",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_governance_plan_completion.py --phase-max 0A",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0A-ci-job",
        "phase": "0A",
        "title": "CI job global-governance-plan-completion wired",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": ".github/workflows/architectural-boundaries.yml global-governance-plan-completion",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-mandate-crosswalk",
        "phase": "0B",
        "title": "GLOBAL_GOVERNANCE_MANDATE_CROSSWALK.md published",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "docs/GLOBAL_GOVERNANCE_MANDATE_CROSSWALK.md",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-audit-findings-register",
        "phase": "0B",
        "title": "Audit findings register + stale doc reconciliation plan",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_governance_doc_truth.py",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-integration-map",
        "phase": "0B",
        "title": "GLOBAL_GOVERNANCE_INTEGRATION_MAP.md",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "docs/GLOBAL_GOVERNANCE_INTEGRATION_MAP.md",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-seven-blind-spots-audit",
        "phase": "0B",
        "title": "Seven global blind spots audited",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_operational_blind_spots.py",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-dissection-waves",
        "phase": "0C",
        "title": "Continental dissection waves — 249/249 verified",
        "agent_lane": "GEO",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_country_dissection_ledger.py --require-verified",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-matrix-249-rows",
        "phase": "0C",
        "title": "country_governance_matrix — full research per ISO",
        "agent_lane": "GEO",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_country_governance_matrix.py --require-verified",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-language-locality-sync",
        "phase": "0C",
        "title": "Matrix languages + terminology synced with seed packs",
        "agent_lane": "LOCALE",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_country_layer_consistency.py",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-country-governance-matrix-md",
        "phase": "0C",
        "title": "COUNTRY_GOVERNANCE_MATRIX.md continental index",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "docs/COUNTRY_GOVERNANCE_MATRIX.md",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-verifiers-bundle",
        "phase": "0D",
        "title": "Phase 0 verifier bundle green",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_governance_plan_completion.py --phase-max 0D",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P0-governance-archetypes",
        "phase": "0D",
        "title": "apps/governance/archetypes.py catalog",
        "agent_lane": "GOV",
        "status": "NOT_DONE",
        "proof": "apps/governance/archetypes.py",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P1-language-overlay-fix",
        "phase": "1",
        "title": "Fix 11-country language overlay regression",
        "agent_lane": "LOCALE",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.siteconfig.tests.test_country_language_overlay_regression",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P1-doc-truth-reconciliation",
        "phase": "1",
        "title": "Campus/EMIS/MAT hub doc truth reconciliation",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_governance_doc_truth.py",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P1-wedge22-mat-hub",
        "phase": "1",
        "title": "Wire wedge 22 to MAT hub nav",
        "agent_lane": "PRODUCT",
        "status": "NOT_DONE",
        "proof": "apps/platform_runtime/wedge_line_registry.py mat-hub link",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P2-governance-org-models",
        "phase": "2A",
        "title": "apps/governance Organization layer models",
        "agent_lane": "GOV",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.governance.tests",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P2-hierarchy-unification",
        "phase": "2B",
        "title": "Unify parent_school, mat_groups, Organization",
        "agent_lane": "GOV",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_hierarchy_silo_drift.py",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P2-operating-modes-wiring",
        "phase": "2B",
        "title": "governance_operating_mode + governance_inherit runtime",
        "agent_lane": "GOV",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_school_operating_modes.py",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P2-exit-gate",
        "phase": "2C",
        "title": "Phase 2 exit gate",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_governance_plan_completion.py --phase-max 2C",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P3-matrix-runtime-wiring",
        "phase": "3A",
        "title": "Wire matrix into signup + statutory hints (249 countries)",
        "agent_lane": "RUNTIME",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.schools.tests.test_governance_matrix_runtime",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P3-subdivisions-all-sovereigns",
        "phase": "3B",
        "title": "ISO 3166-2 subdivision seed for all sovereign states",
        "agent_lane": "GEO",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_subdivision_coverage.py --min-sovereign-pct 100",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P3-context-profiles",
        "phase": "3C",
        "title": "Context Profile layer — multi-role same user",
        "agent_lane": "RUNTIME",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.schools.tests.test_context_profiles",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P3-multi-currency-rollup",
        "phase": "3C",
        "title": "Org-level FX rollup dashboard",
        "agent_lane": "FINANCE",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.finance.tests.test_org_fx_rollup",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P3-litellm-institution-terminology",
        "phase": "3C",
        "title": "LiteLLM + terminology_service institution-type vocabulary",
        "agent_lane": "LOCALE",
        "status": "NOT_DONE",
        "proof": "services/prompt_shaping.py institution terminology wiring",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P3-mc-moe-security-depth",
        "phase": "3D",
        "title": "Migration Cloud + MoE + security annex depth for all countries",
        "agent_lane": "GEO",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_country_layer_consistency.py --mc-depth",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P3-exit-gate",
        "phase": "3E",
        "title": "Phase 3 exit gate",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_governance_plan_completion.py --phase-max 3E",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P4-group-console",
        "phase": "4A",
        "title": "Opt-in Group Console for group_member schools",
        "agent_lane": "PRODUCT",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.schools.tests.test_group_console",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P4-transfer-hr-workflow",
        "phase": "4B",
        "title": "Teacher transfer apply workflow",
        "agent_lane": "GOV",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.interop.tests.test_transfer_apply",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P4-group-billing-fx",
        "phase": "4C",
        "title": "Group billing + consolidated AR",
        "agent_lane": "FINANCE",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.billing.tests.test_group_consolidation",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P4-emis-aggregate-pipeline",
        "phase": "4D",
        "title": "EMIS aggregate pipeline with role-separated reporting",
        "agent_lane": "EMIS",
        "status": "NOT_DONE",
        "proof": "python manage.py test emis.tests.test_org_aggregate",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P4-granular-ops-six-gaps",
        "phase": "4E",
        "title": "Granular ops — SMS router, fast switch, fractional capacity, instruction-day ledger",
        "agent_lane": "OPS",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_operational_blind_spots.py --granular-ops",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P4-staff-compliance-registry",
        "phase": "4F",
        "title": "staff_compliance_registry — clearance expiry blocks attendance",
        "agent_lane": "OPS",
        "status": "NOT_DONE",
        "proof": "python manage.py test apps.people.tests.test_staff_compliance",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P4-exit-gate",
        "phase": "4G",
        "title": "Phase 4 exit gate",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_governance_plan_completion.py --phase-max 4G",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P5-continuous-audit",
        "phase": "5",
        "title": "Continuous matrix drift audit + quarterly benchmark",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_country_governance_matrix.py --drift-check",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "P5-program-closure",
        "phase": "5",
        "title": "Program closure — 100% register DONE or EXTERNAL_BLOCKED",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "python scripts/verify_global_governance_plan_completion.py --strict",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "CROSS-sot-discipline",
        "phase": "CROSS",
        "title": "SOT §11.4 + autonomous log discipline every slice",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §11.4",
        "sot_batch": None,
        "blocked_reason": None,
    },
    {
        "id": "CROSS-multi-agent-coordination",
        "phase": "CROSS",
        "title": "Multi-agent lane coordination protocol",
        "agent_lane": "AUDIT",
        "status": "NOT_DONE",
        "proof": ".cursor/plans/global_governance_audit_582fd47d.plan.md Multi-agent partition",
        "sot_batch": None,
        "blocked_reason": None,
    },
]

P0A_DONE_IDS = frozenset(
    {
        "P0A-completion-register",
        "P0A-aggressive-audit-loop",
        "P0A-matrix-skeleton-249",
        "P0A-dissection-ledger",
        "P0A-verifier-scaffold",
        "P0A-ci-job",
    }
)


def _bootstrap_django() -> None:
    import django

    django.setup()


def _list_iso_countries() -> list[dict[str, str]]:
    from apps.siteconfig.global_catalog import GlobalGeoCatalog

    return GlobalGeoCatalog.list_countries()


def _resolve_pack_tier(alpha2: str) -> str:
    try:
        from apps.siteconfig import _seed_country_localization as seed
        from apps.siteconfig.country_localization_service import resolve_country_pack

        if alpha2 in seed.COUNTRY_LOCALIZATION:
            return "tier1_native"
        pack = resolve_country_pack(alpha2)
        source = str(pack.get("_pack_source") or pack.get("pack_source") or "")
        if "regional" in source:
            return "tier1_regional_clone"
    except Exception:
        pass
    return "generic_fallback"


def _skeleton_terminology() -> dict[str, Any]:
    return {
        "teacher": {"en": "Teacher"},
        "principal": {"en": "Principal"},
        "term": {"en": "Term"},
        "report_card": {"en": "Report card"},
        "grade_level": {"en": "Grade level"},
        "student": {"en": "Student"},
        "classroom": {"en": "Classroom"},
        "ministry_name": {"en": "Ministry of Education"},
        "admin_level_labels": [],
        "school_type_labels": [],
    }


def _country_currency(alpha3: str) -> str:
    from apps.siteconfig.global_catalog import GlobalGeoCatalog

    return GlobalGeoCatalog.country_defaults(alpha3).get("currency", "USD")


def _skeleton_row(country: dict[str, str]) -> dict[str, Any]:
    alpha2 = str(country.get("code_alpha2") or "").upper()
    alpha3 = str(country.get("code") or "").upper()
    continent, wave = continent_and_wave_for_alpha2(alpha2)
    territory = is_likely_territory(alpha2)
    sovereign = not territory
    tier = research_tier_for(alpha2, sovereign=sovereign)
    pack_tier = _resolve_pack_tier(alpha2)
    return {
        "iso_alpha2": alpha2,
        "iso_alpha3": alpha3,
        "name_en": country.get("name") or alpha2,
        "sovereign_state": sovereign,
        "territory": territory,
        "continent": continent,
        "region_bucket": continent.lower().replace(" ", "_"),
        "dissection_wave": wave,
        "dissection_status": "skeleton",
        "governance_archetype": "state_emis_hub" if sovereign else "district_trust_overlay",
        "admin_levels": [] if territory else [{"level": 1, "label_en": "National ministry", "label_local": {}}],
        "employer_model": "school",
        "ownership_types": ["public", "private"],
        "school_structure": "both_common",
        "reporting_chain": ["school"],
        "statutory_framework_ref": None,
        "education_pack_tier": pack_tier,
        "deep_layers": {
            "mc_profile": False,
            "lep": False,
            "moe_preset": False,
            "security_annex": False,
            "subdivisions_seeded": False,
        },
        "languages_expected": [],
        "official_languages": [],
        "education_languages": [],
        "local_terminology": _skeleton_terminology(),
        "name_order": "given-family",
        "address_format_key": "generic",
        "phone_country_code": "",
        "postal_label": "Postal code",
        "grading_scale_family": "generic",
        "calendar_notes": "",
        "terminology_source": "skeleton",
        "locale_catalog_keys": [],
        "customer_risks": ["skeleton_row_requires_dissection"],
        "research_tier": tier,
        "recommended_operating_mode": "standalone",
        "configurable_policy_domains": ["curriculum", "fees", "HR", "branding", "EMIS", "integrations"],
        "currency": _country_currency(alpha3),
        "timezone": country.get("timezone") or "UTC",
    }


def build_matrix(countries: list[dict[str, str]]) -> dict[str, Any]:
    rows = [_skeleton_row(c) for c in countries if c.get("code_alpha2")]
    rows.sort(key=lambda r: r["iso_alpha2"])
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "iso_count": len(rows),
        "rows": rows,
    }


def build_ledger(matrix: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for row in matrix["rows"]:
        entries.append(
            {
                "iso_alpha2": row["iso_alpha2"],
                "continent": row["continent"],
                "wave": row["dissection_wave"],
                "dissection_status": row.get("dissection_status", "skeleton"),
                "research_tier": row.get("research_tier", "T2"),
                "verified_at": None,
            }
        )
    by_wave: dict[str, int] = {}
    for entry in entries:
        by_wave[entry["wave"]] = by_wave.get(entry["wave"], 0) + 1
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "iso_count": len(entries),
        "verified_count": sum(1 for e in entries if e["dissection_status"] == "verified"),
        "by_wave": by_wave,
        "entries": entries,
    }


def build_register(*, mark_p0a_done: bool) -> dict[str, Any]:
    items = []
    for item in REGISTER_ITEMS:
        row = dict(item)
        if mark_p0a_done and row["id"] in P0A_DONE_IDS:
            row["status"] = "DONE"
        items.append(row)
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "NOT_DONE")
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "program": "global_governance_audit",
        "plan_ref": ".cursor/plans/global_governance_audit_582fd47d.plan.md",
        "item_count": len(items),
        "status_counts": counts,
        "items": items,
    }


def write_shards(matrix: dict[str, Any]) -> int:
    MATRIX_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for row in matrix["rows"]:
        iso = row["iso_alpha2"]
        path = MATRIX_DIR / f"{iso}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap global governance Phase 0A artifacts")
    parser.add_argument("--write", action="store_true", help="Write generated JSON artifacts")
    parser.add_argument("--mark-p0a-done", action="store_true", help="Mark Phase 0A register items DONE")
    args = parser.parse_args()

    _bootstrap_django()
    countries = _list_iso_countries()
    if not countries:
        print("FAIL: GlobalGeoCatalog.list_countries() returned empty", file=sys.stderr)
        return 1

    matrix = build_matrix(countries)
    ledger = build_ledger(matrix)
    register = build_register(mark_p0a_done=args.mark_p0a_done)

    print(f"ISO countries: {len(countries)}")
    print(f"Matrix rows: {matrix['iso_count']}")
    print(f"Register items: {register['item_count']}")

    if args.write:
        GENERATED.mkdir(parents=True, exist_ok=True)
        MATRIX_PATH.write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        LEDGER_PATH.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        REGISTER_PATH.write_text(json.dumps(register, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shard_count = write_shards(matrix)
        print(f"Wrote matrix, ledger, register; {shard_count} shards")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
