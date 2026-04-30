#!/usr/bin/env python3
"""
North Star dominance audit (15 sections × 0–5 = /75).

Scores combine:
- SOT North Star slice 15–24 completion (functional gate)
- Key repository path presence
- A fixed set of mechanical verifiers (subprocess)

Exits 1 when total < 70 or when North Star slices 15–24 are not all DONE in SOT
(functional gate cap at 69).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from northstar_common import (
    NORTHSTAR_SLICES,
    count_slices_done,
    ensure_generated_dir,
    json_dump,
    load_sot_text,
    parse_sot_north_star_slice_status,
    path_exists,
    repo_root,
    run_script,
    score_from_exit_ok,
)


SECTION_KEYS = (
    "functional_completeness",
    "security",
    "test_coverage",
    "data_integrity",
    "system_integration",
    "architecture_quality",
    "performance",
    "business_value",
    "ux_quality",
    "reliability",
    "observability",
    "extensibility",
    "global_readiness",
    "ai_readiness",
    "competitive_edge",
)


def rating(total: int) -> str:
    if total >= 75:
        return "DOMINANT"
    if total >= 70:
        return "ELITE"
    if total >= 60:
        return "WEAK"
    return "FAIL"


def main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    root = repo_root()
    sot_text = load_sot_text()
    slice_status = parse_sot_north_star_slice_status(sot_text)
    done_cnt = count_slices_done(slice_status)
    functional_score = round(min(5.0, (done_cnt / len(NORTHSTAR_SLICES)) * 5))

    verifier_notes: dict[str, object] = {}

    # Security surface
    sec = run_script("scripts/audit_security_surface.py")
    verifier_notes["audit_security_surface"] = {"exit_code": sec.returncode}

    # POST / mutation surface ledger (non-strict; use --strict for hard gate)
    post_surf = run_script("scripts/audit_post_surface.py")
    verifier_notes["audit_post_surface"] = {"exit_code": post_surf.returncode}

    rtl = run_script("scripts/verify_rtl_major_templates.py")
    verifier_notes["verify_rtl_major_templates"] = {"exit_code": rtl.returncode}

    reg_ui = run_script("scripts/audit_regional_ui_surface.py")
    verifier_notes["audit_regional_ui_surface"] = {"exit_code": reg_ui.returncode}

    # Tenant isolation
    ti = run_script("scripts/audit_tenant_isolation.py")
    verifier_notes["audit_tenant_isolation"] = {"exit_code": ti.returncode}

    # Architecture / gravity
    ag = run_script("scripts/audit_admin_gravity.py", ["--strict"])
    verifier_notes["audit_admin_gravity_strict"] = {"exit_code": ag.returncode}

    # Raw SQL hotspots visibility
    rs = run_script("scripts/audit_raw_sql_usage.py")
    verifier_notes["audit_raw_sql_usage"] = {"exit_code": rs.returncode}

    # UX / design system + luxury surface gate
    ds = run_script("scripts/verify_design_system_phase2.py")
    verifier_notes["verify_design_system_phase2"] = {"exit_code": ds.returncode}
    lux = run_script("scripts/audit_luxury_ui_surface.py")
    verifier_notes["audit_luxury_ui_surface"] = {"exit_code": lux.returncode}

    # Docs discipline + SOT pillar signals
    dd = run_script("scripts/verify_doc_plan_density_discipline.py")
    verifier_notes["verify_doc_plan_density_discipline"] = {"exit_code": dd.returncode}

    sp = run_script("scripts/verify_sot_pillar_evidence.py")
    verifier_notes["verify_sot_pillar_evidence"] = {"exit_code": sp.returncode}

    tmc = run_script("scripts/verify_test_module_contract.py")
    verifier_notes["verify_test_module_contract"] = {"exit_code": tmc.returncode}
    obs_ledger = run_script("scripts/generate_observability_ledger.py")
    verifier_notes["generate_observability_ledger"] = {"exit_code": obs_ledger.returncode}

    sections: dict[str, dict[str, object]] = {}

    sections["functional_completeness"] = {
        "score": functional_score,
        "rubric": "SOT North Star slice 15–24 with status DONE (max 10).",
        "done_count": done_cnt,
        "expected": len(NORTHSTAR_SLICES),
        "per_slice": {str(k): v for k, v in sorted(slice_status.items())},
    }
    sections["security"] = {
        "score": score_from_exit_ok(sec.returncode),
        "rubric": "audit_security_surface.py exit 0 => 5 else 1",
    }
    _sec_abs = path_exists("apps/security/tests/test_absolute_security_enforcement.py")
    _sec_base = path_exists("apps/security/tests/test_security_enforcement.py")
    sections["test_coverage"] = {
        "score": 5
        if _sec_abs and _sec_base
        else (4 if _sec_base else 2),
        "rubric": "Security regression modules (absolute + base) or weak (2).",
    }
    sections["data_integrity"] = {
        "score": score_from_exit_ok(ti.returncode),
        "rubric": "audit_tenant_isolation.py exit 0 => 5 else 1",
    }
    sections["system_integration"] = {
        "score": 5
        if path_exists("apps/api/api_v1_manifest.py")
        and path_exists("docs/DEVELOPER_PUBLIC_API.md")
        else 2,
        "rubric": "API v1 manifest + public API doc present.",
    }
    sections["architecture_quality"] = {
        "score": score_from_exit_ok(ag.returncode),
        "rubric": "audit_admin_gravity.py --strict",
    }
    sections["performance"] = {
        "score": score_from_exit_ok(rs.returncode),
        "rubric": "audit_raw_sql_usage.py (visibility; 0 exit => 5).",
    }
    _biz_base = path_exists("apps/billing/models.py")
    _biz_advanced = (
        path_exists("apps/platform_runtime/business_value.py")
        and path_exists("apps/schools/super_views_founder_dashboard.py")
        and path_exists("templates/super/founder_dashboard.html")
    )
    sections["business_value"] = {
        "score": 5 if (_biz_base and _biz_advanced) else (4 if _biz_base else 2),
        "rubric": "Billing model + founder business-value metrics surfaces.",
    }
    sections["ux_quality"] = {
        "score": min(
            score_from_exit_ok(ds.returncode),
            score_from_exit_ok(lux.returncode),
        ),
        "rubric": "verify_design_system_phase2.py + audit_luxury_ui_surface.py (>= 13/15 + severe integration)",
    }
    _rel_base = path_exists("apps/observability/models.py") and path_exists(
        "apps/platform_runtime/tests/test_platform_event_log.py"
    )
    _rel_advanced = path_exists("apps/platform_runtime/reliability.py") and path_exists(
        "docs/developer/RELIABILITY_IDEMPOTENCY.md"
    )
    sections["reliability"] = {
        "score": 5 if (_rel_base and _rel_advanced) else (4 if _rel_base else 2),
        "rubric": "Event regression + reliability helper + retry/idempotency docs.",
    }
    _obs_base = path_exists("apps/platform_runtime/observability.py")
    _obs_advanced = (
        obs_ledger.returncode == 0
        and path_exists("scripts/generate_observability_ledger.py")
        and path_exists("docs/generated/observability_ledger.json")
    )
    sections["observability"] = {
        "score": 5 if (_obs_base and _obs_advanced) else (4 if _obs_base else 2),
        "rubric": "Observability helper + generated observability ledger.",
    }
    _ext_base = path_exists("apps/marketplace/manifest_schema.py")
    _ext_advanced = (
        path_exists("apps/marketplace/extension_registry.py")
        and path_exists("docs/developer/WEBHOOK_EVENT_CATALOG.md")
        and tmc.returncode == 0
    )
    sections["extensibility"] = {
        "score": 5 if (_ext_base and _ext_advanced) else (4 if _ext_base else 2),
        "rubric": "Manifest schema + extension registry + webhook catalog + verifier.",
    }
    comp = run_script("scripts/verify_compliance_evidence.py")
    verifier_notes["verify_compliance_evidence"] = {"exit_code": comp.returncode}
    sections["global_readiness"] = {
        "score": min(
            score_from_exit_ok(comp.returncode),
            score_from_exit_ok(rtl.returncode),
            score_from_exit_ok(reg_ui.returncode),
        ),
        "rubric": "verify_compliance_evidence.py + verify_rtl_major_templates.py + audit_regional_ui_surface.py",
    }
    _ai_base = (
        path_exists("apps/platform_runtime/ai_providers.py")
        and path_exists("apps/platform_runtime/tests/test_ai_assistant.py")
        and path_exists("apps/platform_runtime/ai_workflow_bridge.py")
        and path_exists("apps/platform_runtime/tests/test_ai_workflow_bridge.py")
    )
    _ai_advanced = (
        path_exists("apps/platform_runtime/ai_recommendation_registry.py")
        and path_exists("apps/platform_runtime/tests/test_ai_system_layer.py")
        and path_exists("apps/platform_runtime/ai_assistant_service.py")
    )
    sections["ai_readiness"] = {
        "score": 5 if (_ai_base and _ai_advanced) else (4 if _ai_base else 2),
        "rubric": "AI provider + workflow bridge + registry + deterministic safety tests.",
    }
    sections["competitive_edge"] = {
        "score": int(min(5, functional_score + 2)),
        "rubric": "Tied to North Star slice progress (capped) + positioning debt.",
    }

    total = sum(int(s["score"]) for s in sections.values())
    # Block "ELITE/DOMINANT" while any North Star slice 15–24 is not DONE in SOT.
    if done_cnt < len(NORTHSTAR_SLICES):
        total = min(total, 69)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_score": total,
        "max_score": 75,
        "rating": rating(total),
        "sections": sections,
        "verifiers": verifier_notes,
    }
    gen = ensure_generated_dir()
    json_path = gen / "northstar_audit.json"
    md_path = gen / "northstar_audit.md"
    json_dump(out, json_path)

    lines = [
        "# North Star audit",
        "",
        f"**Total:** {total} / 75 — **{out['rating']}**",
        "",
        "| Section | Score |",
        "| --- | ---: |",
    ]
    for key in SECTION_KEYS:
        if key in sections:
            lines.append(f"| {key} | {sections[key]['score']} |")
    lines.extend(
        [
            "",
            "## Slice table (SOT)",
            "",
        ]
    )
    for n in sorted(NORTHSTAR_SLICES):
        st = slice_status.get(n)
        lines.append(f"- Slice {n}: **{st or 'not recorded'}**")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"North Star audit: {total}/75 ({out['rating']}) -> {json_path}")
    if total < 70 or done_cnt < len(NORTHSTAR_SLICES):
        if total < 70:
            print("FAIL: score below 70.", file=sys.stderr)
        else:
            print(
                "FAIL: North Star slices 15–24 not all DONE in SOT (capped below 70).",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
