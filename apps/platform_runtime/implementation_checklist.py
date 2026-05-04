"""Computed implementation checklist from tenant data (no new models)."""

from __future__ import annotations

from typing import Any, Literal

from django.urls import NoReverseMatch, reverse

StatusKind = Literal["ok", "missing", "partial", "unknown"]

# Weights sum to 100 — used for explicit go-live readiness score (honest, checklist-derived).
_READINESS_WEIGHTS: dict[str, int] = {
    "school_profile": 5,
    "academic_year": 10,
    "terms": 10,
    "classes": 10,
    "students": 15,
    "teachers": 15,
    "payment_readiness": 10,
    "portal": 5,
    "offline": 5,
    "reports": 10,
    "go_live": 5,
}


def _rev(url_name: str) -> str | None:
    if not url_name:
        return None
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def build_implementation_checklist(school) -> dict[str, Any]:
    """Return checklist rows and primary next action for *school*."""
    from apps.academics.models import AcademicYear, Classroom, Term
    from apps.finance.models import PaymentGatewayHealthSnapshot
    from apps.people.models import StudentProfile, TeacherProfile
    from apps.schools.models import is_feature_enabled

    rows: list[dict[str, Any]] = []

    def add(
        item_id: str,
        title: str,
        status: StatusKind,
        detail: str,
        *,
        action_label: str,
        url_name: str,
    ):
        url = _rev(url_name) or _rev("siteconfig:dashboard_hub") or "/"
        rows.append(
            {
                "id": item_id,
                "title": title,
                "status": status,
                "detail": detail,
                "primary_action": {"label": action_label, "url": url},
            }
        )

    if school is None:
        add(
            "tenant",
            "Active school tenant",
            "missing",
            "No school resolved for this request.",
            action_label="Open operations home",
            url_name="accounts:backend_dashboard",
        )
        rollup = _readiness_rollup(rows)
        return {
            "items": rows,
            "primary_next_action": rows[0]["primary_action"],
            **rollup,
        }

    add(
        "school_profile",
        "School profile and branding",
        "ok",
        "Tenant record is active; refine branding in configuration surfaces as needed.",
        action_label="Tenant configuration hub",
        url_name="siteconfig:tenant_runtime_configuration_hub",
    )

    ay_exists = AcademicYear.objects.filter(school=school).exists()
    add(
        "academic_year",
        "Academic year",
        "ok" if ay_exists else "missing",
        "At least one academic year should exist before roster and attendance.",
        action_label="Academic years evidence / setup",
        url_name="siteconfig:academic_years_setup_evidence",
    )

    term_ok = Term.objects.filter(school=school).exists()
    st_term: StatusKind = "ok" if term_ok else "missing"
    if not ay_exists:
        st_term = "missing"
    add(
        "terms",
        "Terms / periods",
        st_term,
        "Configure terms for the active academic year.",
        action_label="Academic setup",
        url_name="siteconfig:academic_years_setup_evidence",
    )

    class_count = Classroom.objects.filter(school=school).count()
    st_class: StatusKind = "ok" if class_count else "missing"
    add(
        "classes",
        "Classes / classrooms",
        st_class,
        f"Classrooms detected: {class_count}.",
        action_label="Dashboard hub (academics entry)",
        url_name="siteconfig:dashboard_hub",
    )

    stu_count = (
        StudentProfile.objects.filter(school=school, deleted_at__isnull=True)
        .exclude(status="ALUMNI")
        .count()
    )
    st_stu: StatusKind = "ok" if stu_count else "missing"
    add(
        "students",
        "Students roster",
        st_stu,
        f"Active student profiles: {stu_count}.",
        action_label="People / roster entry",
        url_name="siteconfig:dashboard_hub",
    )

    tc = TeacherProfile.objects.filter(school=school, is_active=True).count()
    st_teach: StatusKind = "ok" if tc else "missing"
    add(
        "teachers",
        "Teachers / staff profiles",
        st_teach,
        f"Active teacher profiles: {tc}.",
        action_label="People / staff entry",
        url_name="siteconfig:dashboard_hub",
    )

    finance_on = is_feature_enabled(school, "finance")
    pay_state: StatusKind = "missing"
    pay_detail = "Enable finance module and configure payment policy when you are ready."
    if finance_on:
        pay_state = "partial"
        pay_detail = "Finance enabled — confirm rails with your PSP externally."
        snap = (
            PaymentGatewayHealthSnapshot.objects.filter(school=school)
            .order_by("-checked_at")
            .first()
        )
        if snap is None:
            pay_detail = "No gateway health snapshot yet (live PSP still external)."
        elif snap.status == PaymentGatewayHealthSnapshot.Status.READY:
            pay_state = "ok"
            pay_detail = "Latest rail check recorded as ready (not a substitute for PSP settlement verification)."
        elif snap.status in (
            PaymentGatewayHealthSnapshot.Status.MISSING_CREDENTIALS,
            PaymentGatewayHealthSnapshot.Status.EXTERNAL_REQUIRED,
        ):
            pay_state = "partial"
            pay_detail = snap.message or "External PSP setup still required for live collections."
        else:
            pay_state = "partial"
            pay_detail = snap.message or "Payment readiness needs follow-up."
    add(
        "payment_readiness",
        "Payment readiness (honest)",
        pay_state,
        pay_detail,
        action_label="Finance dashboard",
        url_name="finance:dashboard",
    )

    portal_ok = is_feature_enabled(school, "portal") or is_feature_enabled(
        school, "parent_portal"
    )
    add(
        "portal",
        "Parent / teacher portal readiness",
        "ok" if portal_ok else "partial",
        "Portal modules help parent and teacher adoption — enable per your plan.",
        action_label="Portal home",
        url_name="accounts:backend_dashboard",
    )

    offline_on = is_feature_enabled(school, "offline") or is_feature_enabled(
        school, "offline_sync"
    )
    add(
        "offline",
        "Offline-first readiness",
        "ok" if offline_on else "partial",
        "Offline queues and conflict tools exist for supported modules; enable features per tenant policy.",
        action_label="Offline sync queue",
        url_name="portal:offline_sync_queue",
    )

    reports_on = is_feature_enabled(school, "reports")
    add(
        "reports",
        "Report card / reporting readiness",
        "ok" if reports_on else "partial",
        "Reporting modules should be entitled before cutover.",
        action_label="Reports entry",
        url_name="accounts:backend_dashboard",
    )

    add(
        "go_live",
        "Leadership go-live sign-off",
        "partial",
        "Confirm communications, training window, and rollback plan with stakeholders.",
        action_label="Support playbooks",
        url_name="platform_runtime:support_playbook_center",
    )

    blockers = [r for r in rows if r["status"] == "missing"]
    partial = [r for r in rows if r["status"] == "partial"]
    if blockers:
        primary_next = blockers[0]["primary_action"]
    elif partial:
        primary_next = partial[0]["primary_action"]
    else:
        primary_next = {
            "label": "Return to lifecycle dashboard",
            "url": _rev("platform_runtime:tenant_lifecycle_dashboard") or "/",
        }

    rollup = _readiness_rollup(rows)
    return {
        "items": rows,
        "primary_next_action": primary_next,
        **rollup,
    }


def _readiness_rollup(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score 0–100, band label, and consolidated blocker list (missing + partial)."""
    total_w = 0
    earned = 0.0
    for r in rows:
        rid = str(r.get("id") or "")
        w = _READINESS_WEIGHTS.get(rid, 0)
        if w <= 0:
            continue
        total_w += w
        st = r.get("status")
        if st == "ok":
            earned += float(w)
        elif st == "partial":
            earned += 0.5 * float(w)
    score = int(round(100.0 * earned / total_w)) if total_w else 0
    if score < 40:
        band = "blocked"
    elif score < 70:
        band = "at_risk"
    elif score < 90:
        band = "progressing"
    else:
        band = "ready"
    missing = [r for r in rows if r.get("status") == "missing"]
    partial = [r for r in rows if r.get("status") == "partial"]
    blockers: list[dict[str, Any]] = []
    for r in missing + partial:
        blockers.append(
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "status": r.get("status"),
                "detail": r.get("detail"),
                "primary_action": r.get("primary_action"),
            }
        )
    return {
        "go_live_readiness_score": score,
        "go_live_readiness_band": band,
        "go_live_readiness_weights_version": 1,
        "consolidated_blockers": blockers,
        "missing_count": len(missing),
        "partial_count": len(partial),
    }
