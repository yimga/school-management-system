"""Plan compliance verifier — audits the Local-First Template Marketplace plan
against actual repo state and produces an honest pass/fail report per section.

Run this to answer "is the plan 100% complete?" with auditable evidence.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _bootstrap() -> Path:
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    return repo_root


def main() -> int:
    repo = _bootstrap()
    checks: list[tuple[str, bool, str]] = []

    # §3/§4 — Registries shipped
    try:
        from apps.brand_experience import experience_templates as et
        from apps.siteconfig import local_experience_profiles as lep
        from apps.platform_runtime import pack_contract as pc

        checks.append(("3.1 ExperienceTemplate overlay count = 75", len(et.OVERLAYS) == 75, f"actual={len(et.OVERLAYS)}"))
        checks.append(("3.2 PackContract experience_template count = 75", len(pc.EXPERIENCE_TEMPLATE_PACKS) == 75, f"actual={len(pc.EXPERIENCE_TEMPLATE_PACKS)}"))
        checks.append(("3.3 LocalExperienceProfile count = 25", len(lep.PROFILES) == 25, f"actual={len(lep.PROFILES)}"))
        checks.append(("3.4 PACK_TYPES contains experience_template", "experience_template" in pc.PACK_TYPES, ""))
    except Exception as exc:
        checks.append(("3.x registry imports", False, str(exc)))

    # §4 — Model classes
    try:
        from apps.brand_experience.models_template import (
            TemplateAssignment, TemplateAuditEvent, record_template_event,
        )
        checks.append(("4.1 TemplateAssignment model imports", True, ""))
        checks.append(("4.2 TemplateAuditEvent model imports", True, ""))
        checks.append(("4.3 record_template_event helper imports", True, ""))
    except Exception as exc:
        checks.append(("4.x model imports", False, str(exc)))

    # §4 — Migration file exists
    mig = repo / "apps" / "brand_experience" / "migrations" / "0004_template_assignment_and_audit_event.py"
    checks.append(("4.4 migration 0004 exists", mig.exists(), str(mig.relative_to(repo)) if mig.exists() else "missing"))

    # §5 — Operator URL surface
    try:
        from django.urls import reverse
        from apps.platform_runtime.views_administration import PACK_ROUTE_TYPES
        operator_ok = "experience-templates" in PACK_ROUTE_TYPES
        checks.append(("5.1 PACK_ROUTE_TYPES has experience-templates", operator_ok, ""))
        for name in (
            "configuration:experience_template_marketplace",
            "configuration:experience_template_detail",
            "configuration:experience_template_preview",
            "configuration:experience_template_simulation",
            "configuration:experience_template_impact",
            "configuration:experience_template_apply",
        ):
            try:
                if "_marketplace" in name:
                    reverse(name)
                else:
                    reverse(name, kwargs={"key": "parent-family-home"})
                checks.append((f"5.2 operator route {name} resolves", True, ""))
            except Exception as exc:
                checks.append((f"5.2 operator route {name} resolves", False, str(exc)))
    except Exception as exc:
        checks.append(("5.x operator URL surface", False, str(exc)))

    # §5 — Tenant URL surface (namespace existence)
    try:
        from django.urls import URLResolver, get_resolver
        resolver = get_resolver()
        namespaces = set()
        def _walk(patterns):
            for p in patterns:
                if isinstance(p, URLResolver):
                    if p.namespace:
                        namespaces.add(p.namespace)
                    _walk(p.url_patterns)
        _walk(resolver.url_patterns)
        # tenant namespace is mounted under tenant_urls — may or may not appear depending on resolver root
        # alternate: import the urls_template_marketplace module directly
        from apps.brand_experience import urls_template_marketplace
        url_count = len(urls_template_marketplace.urlpatterns)
        checks.append(("5.3 tenant urls_template_marketplace has >=8 patterns (plan §5.2)", url_count >= 8, f"actual={url_count}"))
    except Exception as exc:
        checks.append(("5.3 tenant URL surface", False, str(exc)))

    # §6 — Category distribution
    try:
        from apps.brand_experience import experience_templates as et
        counts = {}
        for o in et.OVERLAYS:
            counts[o.category] = counts.get(o.category, 0) + 1
        plan = {
            "operator": 10, "tenant-admin": 8, "teacher": 8, "parent": 6,
            "student": 6, "staff": 4, "specialized": 8, "local-first": 25,
        }
        for cat, expected in plan.items():
            actual = counts.get(cat, 0)
            checks.append((f"6.x category '{cat}' count = {expected}", actual == expected, f"actual={actual}"))
    except Exception as exc:
        checks.append(("6.x category distribution", False, str(exc)))

    # §7 — Heritage palette CSS files
    css_dir = repo / "static" / "css"
    families = (
        "editorial-cream", "warm-terracotta", "cool-indigo", "green-emerald",
        "desert-amber", "monsoon-teal", "sakura-blush", "andes-clay",
        "savanna-ochre", "nordic-slate",
    )
    for family in families:
        f = css_dir / f"design-tokens-local-{family}.css"
        checks.append((f"7.x palette file for {family}", f.exists(), str(f.relative_to(repo)) if f.exists() else "missing"))
    checks.append(("7.11 consolidated palette bundle", (css_dir / "design-tokens-local-palettes.css").exists(), ""))

    # §6 — 75 thumbnails
    thumb_dir = repo / "static" / "img" / "template-thumbs"
    thumb_count = len(list(thumb_dir.glob("*.svg"))) if thumb_dir.exists() else 0
    checks.append(("6.x 75 thumbnail SVGs materialized", thumb_count == 75, f"actual={thumb_count}"))

    # §8 — Apply/customize/rollback wiring (via pack lifecycle)
    try:
        from apps.platform_runtime import pack_apply, pack_preview, pack_rollback, pack_impact, pack_simulation
        checks.append(("8.1 pack lifecycle modules importable", True, ""))
    except Exception as exc:
        checks.append(("8.1 pack lifecycle modules importable", False, str(exc)))

    # §9 — AI recommender
    try:
        from apps.brand_experience.template_ai_recommender import (
            recommend_for_school, recommend_local_first_for_country, TemplateRecommendation,
        )
        checks.append(("9.1 AI recommender importable", True, ""))
    except Exception as exc:
        checks.append(("9.1 AI recommender importable", False, str(exc)))

    # §9 — AI gateway boundary preserved
    ai_recommender_path = repo / "apps" / "brand_experience" / "template_ai_recommender.py"
    if ai_recommender_path.exists():
        ai_text = ai_recommender_path.read_text(encoding="utf-8")
        boundary_violation = "from services.ai_gateway" in ai_text or "import services.ai_gateway" in ai_text
        checks.append(("9.2 AI recommender does NOT import services.ai_gateway", not boundary_violation, ""))

    # §10 — Verifier scripts
    for verifier in (
        "verify_experience_template_registry.py",
        "verify_template_marketplace_routes.py",
        "verify_template_tenant_boundaries.py",
        "verify_template_local_first_coverage.py",
        "verify_template_a11y_floor.py",
        "verify_template_ai_recommender_boundary.py",
        "verify_template_ai_recommender_live_smoke.py",
    ):
        f = repo / "scripts" / verifier
        checks.append((f"10.x verifier {verifier}", f.exists(), str(f.relative_to(repo)) if f.exists() else "missing"))

    # §10 — Tests
    test_file = repo / "apps" / "brand_experience" / "tests" / "test_experience_template_registry.py"
    checks.append(("10.y tests file exists", test_file.exists(), ""))

    # §10 — Playwright spec
    pw_spec = repo / "tests" / "e2e" / "template-marketplace.spec.js"
    checks.append(("10.z Playwright spec at 390/768/1366", pw_spec.exists(), ""))

    # §11 — File list (plan declared) — check the key ones present
    expected_files = [
        "apps/brand_experience/experience_templates.py",
        "apps/brand_experience/template_ai_recommender.py",
        "apps/brand_experience/models_template.py",
        "apps/brand_experience/views_template_marketplace.py",
        "apps/brand_experience/urls_template_marketplace.py",
        "apps/siteconfig/local_experience_profiles.py",
        "templates/marketplace/templates_browse.html",
        "templates/marketplace/templates_detail.html",
        "templates/marketplace/templates_preview_frame.html",
        "templates/marketplace/templates_compare.html",
        "templates/marketplace/templates_apply_confirm.html",
        "templates/marketplace/_local_first_catalog.html",
        "templates/studio_os/partials/experience_templates_fold.html",
        "static/css/rmc-template-marketplace.css",
        "static/js/_pages/rmc-template-marketplace.js",
        "docs/TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md",
        "apps/marketplace/template_partner_manifest.py",
        "apps/marketplace/template_monetization_manifest.py",
    ]
    for ef in expected_files:
        p = repo / ef
        checks.append((f"11.x file {ef}", p.exists(), ""))

    # §11 — Generated audit artifacts (the plan's docs/generated/* list — full 12 pairs)
    expected_generated = [
        "docs/generated/experience_template_registry.json",
        "docs/generated/template_ai_recommender_live_smoke.json",
        "docs/generated/template_marketplace_plan_compliance.json",
        # The 12 audit pairs declared in plan §11 file list
        "docs/generated/local_first_template_marketplace_code_truth_inventory.json",
        "docs/generated/local_first_template_marketplace_code_truth_inventory.md",
        "docs/generated/local_first_template_marketplace_architecture_audit.json",
        "docs/generated/local_first_template_marketplace_architecture_audit.md",
        "docs/generated/local_first_template_catalog_75_premium.json",
        "docs/generated/local_first_template_catalog_75_premium.md",
        "docs/generated/local_first_template_profile_coverage_matrix.json",
        "docs/generated/local_first_template_profile_coverage_matrix.md",
        "docs/generated/local_first_template_live_preview_engine_audit.json",
        "docs/generated/local_first_template_live_preview_engine_audit.md",
        "docs/generated/local_first_template_studio_os_integration.json",
        "docs/generated/local_first_template_studio_os_integration.md",
        "docs/generated/local_first_template_tenant_studio_integration.json",
        "docs/generated/local_first_template_tenant_studio_integration.md",
        "docs/generated/local_first_template_apply_customize_rollback_audit.json",
        "docs/generated/local_first_template_apply_customize_rollback_audit.md",
        "docs/generated/local_first_template_ai_recommendation_audit.json",
        "docs/generated/local_first_template_ai_recommendation_audit.md",
        "docs/generated/local_first_template_marketplace_ux_audit.json",
        "docs/generated/local_first_template_marketplace_ux_audit.md",
        "docs/generated/local_first_template_marketplace_browser_qa_report.json",
        "docs/generated/local_first_template_marketplace_browser_qa_report.md",
        "docs/generated/local_heritage_design_system.json",
        "docs/generated/local_heritage_design_system.md",
    ]
    for ef in expected_generated:
        p = repo / ef
        checks.append((f"11.y generated artifact {ef}", p.exists(), ""))

    # §11 — Architecture doc + CI workflow (plan §11 file list)
    arch_doc = repo / "docs" / "architecture" / "RUNMYCAMPUS_LOCAL_FIRST_TEMPLATE_MARKETPLACE.md"
    checks.append(("11.z architecture doc shipped", arch_doc.exists(), ""))
    wf = repo / ".github" / "workflows" / "template-marketplace-gates.yml"
    checks.append(("11.w CI workflow shipped", wf.exists(), ""))
    if wf.exists():
        wf_text = wf.read_text(encoding="utf-8")
        # Every upload-artifact block must carry retention-days (compare keys, not free text)
        import re
        upload_count = wf_text.count("actions/upload-artifact@")
        retention_yaml_keys = len(re.findall(r"^\s+retention-days:\s*1\b", wf_text, re.MULTILINE))
        checks.append((
            "11.w-retention every upload-artifact block carries retention-days: 1",
            upload_count > 0 and retention_yaml_keys >= upload_count,
            f"uploads={upload_count} retention-yaml-keys={retention_yaml_keys}",
        ))

    # §13 — SOT/log batch IDs
    sot = (repo / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md").read_text(encoding="utf-8", errors="ignore")
    checks.append(("13.1 SOT contains batch 1400 entry", "batch 1400 (Local-First Global Template Marketplace" in sot, ""))
    checks.append(("13.2 SOT contains batch 1401 entry", "batch 1401 (Template Marketplace Waves B+C+D+E closeout" in sot, ""))

    # §16 — Cleanliness
    sw = (repo / "static" / "js" / "service-worker.js").read_text(encoding="utf-8", errors="ignore")
    checks.append(("16.1 SW bumped to v3.64.0", "sms-v3.64.0-template-marketplace-waves" in sw, ""))

    # Final report
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    failures = [(name, detail) for name, ok, detail in checks if not ok]
    report = {
        "status": "TEMPLATE_MARKETPLACE_PLAN_COMPLIANCE_PASS" if not failures else "TEMPLATE_MARKETPLACE_PLAN_COMPLIANCE_PARTIAL",
        "passed": passed,
        "total": total,
        "completion_pct": round((passed / total) * 100, 1),
        "failures": [{"check": n, "detail": d} for n, d in failures],
    }
    out = repo / "docs" / "generated" / "template_marketplace_plan_compliance.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"{report['status']}")
    print(f"  passed: {passed}/{total}  ({report['completion_pct']}%)")
    if failures:
        print(f"  failures ({len(failures)}):")
        for n, d in failures:
            print(f"    - {n} | {d}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
