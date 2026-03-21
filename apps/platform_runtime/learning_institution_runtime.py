"""
Bind SOT wedges 23–30 / 31–43 to tenant runtime: features, settings, workflow/report hints.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.platform_runtime.learning_institution_catalog import (
    CATALOG_VERSION,
    INSTITUTION_TYPE_PACKS,
    LEARNING_DELIVERY_MODES,
    MINISTRY_REPORT_STUBS,
    normalize_delivery_code,
    normalize_institution_code,
)

logger = logging.getLogger(__name__)

# Pack slug → feature flags (advisory; policies may still gate)
PACK_FEATURE_MAP: dict[str, list[str]] = {
    "core_scheduling": ["timetable", "scheduling"],
    "attendance_classroom": ["attendance", "room_attendance"],
    "room_resources": ["room_booking"],
    "lms_lti_bridge": ["lti_launch", "section8_lti"],
    "video_conferencing": ["video_conferencing"],
    "portal_comms": ["parent_portal", "communication_center"],
    "evals_continuous": ["continuous_assessment", "evals"],
    "evals_rubrics": ["rubrics", "evals"],
    "degree_audit_he": ["he_degree_audit", "degree_audit"],
    "progression_gates": ["mastery_gates", "retake_policy"],
    "portfolio_evidence": ["portfolios", "evidence_trail"],
    "team_projects": ["group_projects"],
    "async_content": ["async_lms"],
    "cohort_progress": ["cohort_analytics"],
    "term_rollover": ["rollover_wizard"],
    "starter_k12": ["k12_core"],
    "region_curriculum": ["regional_curriculum"],
    "tvet_hours": ["tvet", "workplace_learning"],
    "competency_modules": ["competency_tracking"],
    "workplace_learning": ["workplace_learning"],
    "employer_portal": ["employer_verify"],
    "dual_transcript": ["dual_transcript"],
    "specialty_tracks": ["specialty_programs"],
    "facilities_booking": ["facilities"],
    "talent_pathways": ["talent_path"],
    "early_years_observations": ["early_years"],
    "parent_portal_light": ["parent_portal"],
    "developmental_milestones": ["eyfs_milestones"],
    "session_based_enrollment": ["session_enrollment"],
    "flexible_billing": ["flexible_billing"],
    "evening_scheduling": ["evening_classes"],
    "credential_tracking": ["credentials"],
    "cohort_training": ["corporate_cohorts"],
    "compliance_credits": ["compliance_pd"],
    "level_placement": ["placement_tests"],
    "session_cycles": ["session_cycles"],
    "multi_language_reports": ["multilingual_reports"],
    "session_packages": ["tutoring_packages"],
    "outcome_tracking": ["exam_outcomes"],
    "small_group_scheduling": ["small_group"],
    "iep_tracking": ["iep", "special_ed"],
    "accommodations": ["accommodations"],
    "multi_discipline_team": ["mdt_meetings"],
    "acceleration_paths": ["acceleration"],
    "enrichment_catalog": ["enrichment"],
    "differentiation": ["differentiation"],
    "flexible_attendance": ["flex_attendance"],
    "outreach_logging": ["outreach"],
    "safeguarding_escalation": ["safeguarding"],
    "degree_audit": ["degree_audit"],
    "semester_catalog": ["semester_catalog"],
    "graduate_research": ["graduate_research"],
    "ib_igcse_paths": ["international_curriculum"],
    "custom_terms": ["custom_terms"],
    "community_events": ["community_events"],
}


def _hints_for_slugs(slugs: list[str]) -> tuple[list[str], list[str]]:
    workflows: list[str] = []
    reports: list[str] = []
    for s in slugs:
        s = s.strip()
        if not s:
            continue
        workflows.append(f"workflow_hint:{s}")
        reports.append(f"report_stub:{s}")
    return workflows, reports


def apply_learning_institution_packs(
    school,
    *,
    delivery_mode_codes: list[str] | None = None,
    institution_type_code: str | None = None,
) -> dict[str, Any]:
    settings = dict(school.settings or {})
    features = dict(school.features or {})
    wedges_d: list[int] = []
    all_pack_slugs: list[str] = []

    if delivery_mode_codes:
        normalized = [normalize_delivery_code(c) for c in delivery_mode_codes]
        settings["learning_delivery_modes"] = normalized
        for code in normalized:
            row = next((m for m in LEARNING_DELIVERY_MODES if m["code"] == code), None)
            if row:
                wedges_d.append(int(row["wedge"]))
                for slug in str(row.get("pack_slugs") or "").split(","):
                    slug = slug.strip()
                    if slug:
                        all_pack_slugs.append(slug)
                    for feat in PACK_FEATURE_MAP.get(slug, [slug] if slug else []):
                        if feat:
                            features[str(feat)] = True
        settings["learning_delivery_wedges"] = sorted(set(wedges_d))

    if institution_type_code:
        code = normalize_institution_code(institution_type_code)
        settings["institution_type_pack"] = code
        row = next((p for p in INSTITUTION_TYPE_PACKS if p["code"] == code), None)
        if row:
            settings["institution_type_wedge"] = int(row["wedge"])
            for slug in str(row.get("pack_slugs") or "").split(","):
                slug = slug.strip()
                if slug:
                    all_pack_slugs.append(slug)
                for feat in PACK_FEATURE_MAP.get(slug, [slug] if slug else []):
                    if feat:
                        features[str(feat)] = True
            stubs = MINISTRY_REPORT_STUBS.get(code) or MINISTRY_REPORT_STUBS.get(
                "DEFAULT", []
            )
            settings["ministry_report_stub_slugs"] = [x["slug"] for x in stubs]

    wf, rp = _hints_for_slugs(list(dict.fromkeys(all_pack_slugs)))
    if wf:
        existing = list(settings.get("workflow_pack_hints") or [])
        settings["workflow_pack_hints"] = list(dict.fromkeys(existing + wf))[-50:]
    if rp:
        existing_r = list(settings.get("report_template_hints") or [])
        settings["report_template_hints"] = list(dict.fromkeys(existing_r + rp))[-50:]

    school.settings = settings
    school.features = features
    school.save(update_fields=["settings", "features", "updated_at"])
    try:
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "learning_institution_packs_applied",
            {
                "school_id": str(school.id),
                "delivery_wedges": settings.get("learning_delivery_wedges"),
                "institution_wedge": settings.get("institution_type_wedge"),
                "pack_slugs": list(dict.fromkeys(all_pack_slugs))[-50:],
            },
            tenant_id=str(getattr(school, "id", "") or ""),
            school_id=None,
            idempotency_key=f"li-packs:{school.id}:{hash(tuple(all_pack_slugs)) & 0xFFFFFFFF}",
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return {
        "delivery_wedges": settings.get("learning_delivery_wedges"),
        "institution_wedge": settings.get("institution_type_wedge"),
        "feature_keys": [k for k, v in features.items() if v],
    }


def all_catalog_pack_slugs() -> set[str]:
    out: set[str] = set()
    for row in LEARNING_DELIVERY_MODES:
        for s in str(row.get("pack_slugs") or "").split(","):
            s = s.strip()
            if s:
                out.add(s)
    for row in INSTITUTION_TYPE_PACKS:
        for s in str(row.get("pack_slugs") or "").split(","):
            s = s.strip()
            if s:
                out.add(s)
    out.update(PACK_FEATURE_MAP.keys())
    return out


def apply_single_wedge_pack_slug(school, pack_slug: str) -> dict[str, Any]:
    """
    One-click / marketplace: merge a single catalog pack slug into tenant features and audit list.
    """
    slug = (pack_slug or "").strip()
    if not slug or slug not in all_catalog_pack_slugs():
        raise ValueError(f"Unknown wedge pack slug: {pack_slug!r}")
    features = dict(school.features or {})
    for feat in PACK_FEATURE_MAP.get(slug, [slug]):
        if feat:
            features[str(feat)] = True
    features[f"wedge_pack_{slug}"] = True
    settings = dict(school.settings or {})
    installs = list(settings.get("wedge_marketplace_installs") or [])
    if slug not in installs:
        installs.append(slug)
    settings["wedge_marketplace_installs"] = installs[-100:]
    school.features = features
    school.settings = settings
    school.save(update_fields=["settings", "features", "updated_at"])
    try:
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "learning_wedge_pack_applied",
            {"school_id": str(school.id), "pack_slug": slug},
            tenant_id=str(getattr(school, "id", "") or ""),
            school_id=None,
            idempotency_key=f"wedge-pack:{school.id}:{slug}",
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    try:
        from apps.metadata.usage_registry import register_usage

        register_usage("wedge_pack", f"pack:{slug}", "tenant_learning_wedge", slug)
        for feat in PACK_FEATURE_MAP.get(slug, [slug])[:20]:
            if feat:
                register_usage(
                    "wedge_pack", f"pack:{slug}", "tenant_feature_flag", str(feat)
                )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return {
        "pack_slug": slug,
        "feature_keys_touched": list(PACK_FEATURE_MAP.get(slug, [slug])),
    }


def rollback_single_wedge_pack_slug(
    school,
    pack_slug: str,
    *,
    sync_marketplace: bool = True,
    uninstalled_by=None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """
    Remove a single wedge pack from tenant features/settings.

    Feature flags mapped by this pack are set False only when no other wedge in
    ``wedge_marketplace_installs`` still requires them (shared-feature safe).
    """
    slug = (pack_slug or "").strip()
    if not slug or slug not in all_catalog_pack_slugs():
        raise ValueError(f"Unknown wedge pack slug: {pack_slug!r}")
    features = dict(school.features or {})
    settings = dict(school.settings or {})
    installs = list(settings.get("wedge_marketplace_installs") or [])
    wedge_key = f"wedge_pack_{slug}"
    if slug not in installs and not features.get(wedge_key):
        raise ValueError(f"Wedge pack not recorded as installed: {slug!r}")

    new_installs = [x for x in installs if x != slug]
    settings["wedge_marketplace_installs"] = new_installs[-100:]

    needed_features: set[str] = set()
    for s in new_installs:
        for feat in PACK_FEATURE_MAP.get(s, [s]):
            if feat:
                needed_features.add(str(feat))

    touched = list(PACK_FEATURE_MAP.get(slug, [slug]))
    cleared: list[str] = []
    for feat in touched:
        if not feat:
            continue
        fs = str(feat)
        if fs not in needed_features:
            features[fs] = False
            cleared.append(fs)

    features[wedge_key] = False
    school.features = features
    school.settings = settings
    school.save(update_fields=["settings", "features", "updated_at"])

    if sync_marketplace:
        try:
            from apps.marketplace.models import AppInstallation, MarketplaceApp

            from apps.marketplace.services import uninstall_app

            app_slug = f"wedge-pack-{slug.replace('_', '-')}"[:80]
            app = MarketplaceApp.objects.filter(slug=app_slug).first()
            if app:
                inst = AppInstallation.objects.filter(
                    school=school,
                    app=app,
                    status=AppInstallation.Status.ACTIVE,
                ).first()
                if inst:
                    uninstall_app(school, app, uninstalled_by=uninstalled_by)
        except Exception:
            logger.debug("wedge rollback marketplace sync skipped", exc_info=True)

    try:
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "learning_wedge_pack_rolled_back",
            {
                "school_id": str(school.id),
                "pack_slug": slug,
                "actor_id": actor_id,
                "features_cleared": cleared,
            },
            tenant_id=str(getattr(school, "id", "") or ""),
            school_id=None,
            idempotency_key=f"wedge-rollback:{school.id}:{slug}",
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    return {
        "pack_slug": slug,
        "features_cleared": cleared,
        "wedge_marketplace_installs": settings["wedge_marketplace_installs"],
    }


def install_wedge_pack_with_marketplace_record(
    school, pack_slug: str, *, installed_by=None
) -> dict[str, Any]:
    """Record a first-party MarketplaceApp install then apply pack (one-click path)."""
    from apps.marketplace.models import MarketplaceApp, PublisherOrganization
    from apps.marketplace.services import install_app

    slug = (pack_slug or "").strip()
    apply_single_wedge_pack_slug(school, slug)
    pub, _ = PublisherOrganization.objects.get_or_create(
        slug="runmycampus-wedge-packs",
        defaults={
            "name": "RunMyCampus wedge packs",
            "verification_status": PublisherOrganization.VerificationStatus.VERIFIED,
        },
    )
    app_slug = f"wedge-pack-{slug.replace('_', '-')}"[:80]
    app, _ = MarketplaceApp.objects.get_or_create(
        slug=app_slug,
        defaults={
            "publisher": pub,
            "name": f"Pack: {slug}",
            "description": "Learning institution wedge pack (SOT 23–43).",
            "version": CATALOG_VERSION,
            "manifest": {"wedge_pack_slug": slug, "catalog_version": CATALOG_VERSION},
            "kind": MarketplaceApp.AppKind.FIRST_PARTY,
            "is_active": True,
        },
    )
    install_app(school, app, installed_by=installed_by, skip_compatibility=True)
    return {
        "pack_slug": slug,
        "marketplace_app_slug": app.slug,
        "catalog_version": CATALOG_VERSION,
    }


def suggest_institution_profile_from_school(school) -> dict[str, Any]:
    """
    AI/heuristic institution profile suggestion (no PII in external calls; heuristic works offline).
    """
    name = (getattr(school, "name", None) or "").lower()
    region = ""
    try:
        dr = getattr(school, "default_region", None)
        region = (getattr(dr, "code", None) or "") if dr else ""
    except (AttributeError, TypeError):
        region = ""
    delivery = ["W23_IN_PERSON"]
    inst = "W31_GENERAL_K12"
    if any(x in name for x in ("university", "college", "polytechnic", "faculty")):
        inst = "W43_HIGHER_EDUCATION"
        delivery = ["W30_COHORT_BASED", "W29_SELF_PACED"]
    elif any(x in name for x in ("language", "ielts", "toefl")):
        inst = "W38_LANGUAGE_SCHOOL"
    elif any(x in name for x in ("tvet", "vocational", "technical college")):
        inst = "W32_TVET"
    elif any(x in name for x in ("nursery", "pre-k", "kindergarten", "early years")):
        inst = "W35_EARLY_YEARS"
    elif any(x in name for x in ("tutor", "prep", "coaching")):
        inst = "W39_EXAM_PREP_TUTORING"
    elif any(x in name for x in ("online", "virtual academy", "distance")):
        delivery = ["W24_FULLY_ONLINE", "W29_SELF_PACED"]
    if region in ("GBR", "GB"):
        pass
    return {
        "delivery_mode_codes": delivery,
        "institution_type_code": inst,
        "confidence": 0.55 if inst == "W31_GENERAL_K12" else 0.72,
        "source": "heuristic",
        "catalog_version": CATALOG_VERSION,
    }


def aggregate_learning_wedge_benchmarks() -> dict[str, Any]:
    """Anonymized cross-tenant stats for super dashboards (counts only, no school names)."""
    from apps.schools.models import School

    qs = School.objects.filter(is_active=True)
    total = qs.count()
    by_inst = {}
    by_delivery_count = 0
    for sch in qs.only("id", "settings").iterator(chunk_size=200):
        st = sch.settings or {}
        ic = (st.get("institution_type_pack") or "").strip().upper()
        if ic:
            by_inst[ic] = by_inst.get(ic, 0) + 1
        modes = st.get("learning_delivery_modes") or []
        if modes:
            by_delivery_count += 1
    return {
        "catalog_version": CATALOG_VERSION,
        "active_schools_total": total,
        "schools_with_delivery_modes_configured": by_delivery_count,
        "schools_by_institution_type_code": by_inst,
    }
