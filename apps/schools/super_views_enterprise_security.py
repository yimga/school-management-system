"""
Enterprise security hub: /super/security/ — alerts, audit tails, session visibility (operator).

Loads generated verifier JSON from docs/generated/* for a consolidated governance strip (no secrets).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.contrib.sessions.models import Session
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.accounts.models import SecurityAuditLog, User


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).resolve()


def _load_generated_json(rel_under_repo: str) -> dict:
    path = _repo_root() / rel_under_repo
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _export_audit_integrity_token(log) -> str:
    """
    Deterministic HMAC over audit row identity fields (not file bytes).
    Operators verify the log row was not tampered with offline using the same key.
    """
    msg = "|".join(
        [
            str(log.pk),
            log.timestamp.isoformat() if log.timestamp else "",
            str(log.action),
            str(log.user_id or ""),
            str(log.model_name or ""),
            str(log.object_id or ""),
            str(log.object_repr or ""),
            str(log.app_label or ""),
        ]
    )
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]


def _school_hint_for_export(log) -> str:
    """Best-effort tenant label for export timeline (no cross-tenant bulk prefetch)."""
    try:
        if getattr(log, "model_name", None) == "School" and log.object_id:
            from apps.schools.models import School

            s = School.objects.filter(pk=log.object_id).only("name").first()
            if s:
                return s.name
    except Exception:
        pass
    nv = log.new_values or {}
    if isinstance(nv, dict):
        for key in ("school_name", "tenant_name", "school_slug"):
            v = nv.get(key)
            if v:
                return str(v)[:120]
    return "—"


def _build_export_timeline_rows(logs: list) -> list[dict]:
    rows = []
    for log in logs:
        rows.append(
            {
                "timestamp": log.timestamp,
                "actor_username": (
                    log.user.get_username() if getattr(log, "user", None) else "—"
                ),
                "school_tenant": _school_hint_for_export(log),
                "export_type": log.model_name,
                "filter_summary": (log.object_repr or "")[:240],
                "status": "recorded",
                "integrity_token": _export_audit_integrity_token(log),
                "verification_state": "hmac-bound",
            }
        )
    return rows


def _summarize_verifier_artifacts() -> dict:
    """Read-only summaries for operator dashboard (paths are repo-relative)."""
    sec = _load_generated_json("docs/generated/security_surface_audit.json")
    post = _load_generated_json("docs/generated/post_surface_audit.json")
    tenant = _load_generated_json("docs/generated/tenant_isolation_audit.json")
    raw_sql = _load_generated_json("docs/generated/raw_sql_audit.json")
    subprocess = _load_generated_json("docs/generated/subprocess_audit.json")
    gilead = _load_generated_json("docs/generated/gilead_reference_audit.json")
    route = _load_generated_json("docs/generated/route_surface_audit.json")
    compliance = _load_generated_json("docs/generated/compliance_evidence_ledger.json")
    kill_test = _load_generated_json("docs/generated/kill_test_report.json")
    northstar = _load_generated_json("docs/generated/northstar_audit.json")
    test_contract = _load_generated_json("docs/generated/test_module_contract.json")

    def _hits(d: dict) -> str | None:
        t = d.get("totals") if isinstance(d.get("totals"), dict) else {}
        h = t.get("hits")
        return str(h) if h is not None else None

    gtot = gilead.get("totals") if isinstance(gilead.get("totals"), dict) else {}
    pub_v = gtot.get("public_ui_violations")

    route_summary = (
        route.get("summary") if isinstance(route.get("summary"), dict) else {}
    )
    rs_status = route_summary.get("status")
    rs_broken = route_summary.get("broken_count")

    kt_result = kill_test.get("result")
    kt_crit = kill_test.get("critical_count")
    ns_rating = northstar.get("rating")
    ns_score = northstar.get("max_score")
    t_ok = test_contract.get("ok")
    t_rows = test_contract.get("map_rows")

    missing = []
    for label, blob in (
        ("security_surface_audit.json", sec),
        ("post_surface_audit.json", post),
        ("tenant_isolation_audit.json", tenant),
        ("raw_sql_audit.json", raw_sql),
        ("subprocess_audit.json", subprocess),
        ("gilead_reference_audit.json", gilead),
        ("route_surface_audit.json", route),
        ("compliance_evidence_ledger.json", compliance),
        ("kill_test_report.json", kill_test),
        ("northstar_audit.json", northstar),
        ("test_module_contract.json", test_contract),
    ):
        if not blob:
            missing.append(label)

    cards = [
        {
            "id": "security_surface",
            "label": "Route / security scan",
            "present": bool(sec),
            "summary": _hits(sec) or "—",
            "generated_at": sec.get("generated_at"),
        },
        {
            "id": "post_csrf",
            "label": "POST / CSRF ledger",
            "present": bool(post),
            "summary": (
                str((post.get("summary") or {}).get("product_needs_review", "—"))
                if post
                else "—"
            ),
            "generated_at": post.get("generated_at"),
        },
        {
            "id": "tenant_isolation",
            "label": "Tenant isolation scan",
            "present": bool(tenant),
            "summary": _hits(tenant) or "—",
            "generated_at": tenant.get("generated_at"),
        },
        {
            "id": "raw_sql",
            "label": "Raw SQL audit",
            "present": bool(raw_sql),
            "summary": _hits(raw_sql) or "—",
            "generated_at": raw_sql.get("generated_at"),
        },
        {
            "id": "subprocess",
            "label": "Subprocess audit",
            "present": bool(subprocess),
            "summary": _hits(subprocess) or "—",
            "generated_at": subprocess.get("generated_at"),
        },
        {
            "id": "gilead_public",
            "label": "Gilead refs (strict-public)",
            "present": bool(gilead),
            "summary": (
                f"hits {_hits(gilead) or '—'}, public_ui_violations {pub_v if pub_v is not None else '—'}"
                if gilead
                else "—"
            ),
            "generated_at": gilead.get("generated_at"),
        },
        {
            "id": "route_cert",
            "label": "Route surface certification",
            "present": bool(route),
            "summary": (
                f"{rs_status or '—'} · broken {rs_broken if rs_broken is not None else '—'}"
                if route
                else "—"
            ),
            "generated_at": route.get("generated_at"),
        },
        {
            "id": "compliance_evidence",
            "label": "Compliance evidence ledger",
            "present": bool(compliance),
            "summary": (
                f"schema v{compliance.get('schema_version', '?')} · "
                f"{len(compliance.get('evidence') or [])} evidence rows"
                if compliance
                else "—"
            ),
            "generated_at": compliance.get("generated_at"),
        },
        {
            "id": "kill_test",
            "label": "Kill test regression",
            "present": bool(kill_test),
            "summary": (
                f"{kt_result or '—'} · critical {kt_crit if kt_crit is not None else '—'}"
                if kill_test
                else "—"
            ),
            "generated_at": kill_test.get("generated_at"),
        },
        {
            "id": "northstar_audit",
            "label": "North Star audit",
            "present": bool(northstar),
            "summary": (
                f"{ns_rating or '—'} / max {ns_score if ns_score is not None else '—'}"
                if northstar
                else "—"
            ),
            "generated_at": northstar.get("generated_at"),
        },
        {
            "id": "test_module_contract",
            "label": "Test module contract",
            "present": bool(test_contract),
            "summary": (
                f"ok={t_ok} · map_rows {t_rows if t_rows is not None else '—'}"
                if test_contract
                else "—"
            ),
            "generated_at": test_contract.get("generated_at"),
        },
    ]

    risk_groups = []
    if missing:
        risk_groups.append(
            {
                "id": "missing_ledgers",
                "title": "Missing generated governance files",
                "detail": ", ".join(missing[:12])
                + ("…" if len(missing) > 12 else ""),
                "action_label": "Open static security surface",
                "action_url": reverse("super:security_surface_dashboard"),
            }
        )
    if route and rs_broken not in (None, 0):
        risk_groups.append(
            {
                "id": "route_broken",
                "title": "Route certification reports broken reverses",
                "detail": f"broken_count={rs_broken}",
                "action_label": "Review route audit JSON",
                "action_url": reverse("super:security_surface_dashboard"),
            }
        )
    if gilead and pub_v not in (None, 0):
        risk_groups.append(
            {
                "id": "gilead_public_ui",
                "title": "Public UI Gilead reference violations",
                "detail": f"public_ui_violations={pub_v}",
                "action_label": "Run audit_gilead_references --strict-public",
                "action_url": reverse("super:security_surface_dashboard"),
            }
        )
    if kill_test and str(kt_result or "") not in ("", "PASS"):
        risk_groups.append(
            {
                "id": "kill_test_fail",
                "title": "Kill test regression reported failures",
                "detail": f"result={kt_result!r} · critical={kt_crit!r}",
                "action_label": "Review kill test report",
                "action_url": reverse("super:security_surface_dashboard"),
            }
        )

    return {
        "cards": cards,
        "missing_files": missing,
        "risk_groups": risk_groups,
        "route_broken_count": rs_broken,
        "gilead_public_violations": pub_v,
    }


def _decode_session_user_ids(limit: int = 150):
    """Recent non-expired sessions with resolved user emails (best-effort)."""
    now = timezone.now()
    rows = []
    sessions = (
        Session.objects.filter(expire_date__gte=now).order_by("-expire_date")[:limit]
    )
    for s in sessions:
        uid = None
        email = "—"
        try:
            data = s.get_decoded()
            uid = data.get("_auth_user_id")
            if uid:
                u = User.objects.filter(pk=uid).only("email", "username").first()
                if u:
                    email = getattr(u, "email", "") or getattr(u, "username", "") or str(
                        uid
                    )
        except Exception:
            pass
        rows.append(
            {
                "session_key_prefix": (s.session_key or "")[:8] + "…",
                "expire_date": s.expire_date,
                "user_id": uid,
                "user_label": email,
            }
        )
    return rows


@require_GET
def super_security_hub(request):
    """Primary operator security dashboard: links + recent signals + audit tails."""
    dashboard_url = reverse("super:dashboard")
    surface_url = reverse("super:security_surface_dashboard")

    cutoff_7d = timezone.now() - timedelta(days=7)

    security_events = list(
        SecurityAuditLog.objects.select_related("user", "school")
        .order_by("-created_at")[:80]
    )

    suspicious_security_events = list(
        SecurityAuditLog.objects.filter(
            is_suspicious=True,
            created_at__gte=cutoff_7d,
        )
        .select_related("user", "school")
        .order_by("-created_at")[:60]
    )
    suspicious_count_7d = SecurityAuditLog.objects.filter(
        is_suspicious=True,
        created_at__gte=cutoff_7d,
    ).count()
    impossible_travel_7d = SecurityAuditLog.objects.filter(
        event_type=SecurityAuditLog.EventType.IMPOSSIBLE_TRAVEL,
        created_at__gte=cutoff_7d,
    ).count()

    perm_events = []
    export_events = []
    export_timeline_rows: list[dict] = []
    access_denied_events = []
    approval_events = []
    try:
        from apps.compliance.models_audit import AuditLog

        perm_events = list(
            AuditLog.objects.filter(
                Q(
                    action__in=(
                        AuditLog.Action.PERMISSION_GRANT,
                        AuditLog.Action.PERMISSION_REVOKE,
                    )
                )
                | Q(
                    model_name="SchoolMembership",
                    action=AuditLog.Action.UPDATE,
                )
            )
            .select_related("user")
            .order_by("-timestamp")[:40]
        )
        export_events = list(
            AuditLog.objects.filter(action=AuditLog.Action.EXPORT)
            .select_related("user")
            .order_by("-timestamp")[:40]
        )
        export_timeline_rows = _build_export_timeline_rows(export_events)
        access_denied_events = list(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED)
            .select_related("user")
            .order_by("-timestamp")[:40]
        )
        approval_events = list(
            AuditLog.objects.filter(action=AuditLog.Action.APPROVE)
            .select_related("user")
            .order_by("-timestamp")[:25]
        )
    except Exception:
        pass

    session_rows = _decode_session_user_ids(120)

    verifier_ctx = _summarize_verifier_artifacts()

    impersonation_rows = []
    try:
        from apps.siteconfig.models import ImpersonationLog

        impersonation_rows = list(
            ImpersonationLog.objects.select_related("actor", "peer_actor", "school")
            .order_by("-created_at")[:40]
        )
    except Exception:
        pass

    admin_security_audit_url = None
    admin_auditlog_url = None
    if getattr(request.user, "is_superuser", False):
        try:
            admin_security_audit_url = reverse(
                "admin:accounts_securityauditlog_changelist"
            )
        except Exception:
            pass
        try:
            admin_auditlog_url = reverse("admin:compliance_auditlog_changelist")
        except Exception:
            pass

    return render(
        request,
        "schools/super_security_hub.html",
        {
            "page_title": "Security & audit",
            "dashboard_url": dashboard_url,
            "security_surface_url": surface_url,
            "support_dashboard_url": reverse("super:support_dashboard"),
            "security_events": security_events,
            "suspicious_security_events": suspicious_security_events,
            "suspicious_count_7d": suspicious_count_7d,
            "impossible_travel_7d": impossible_travel_7d,
            "perm_events": perm_events,
            "export_events": export_events,
            "export_timeline_rows": export_timeline_rows,
            "access_denied_events": access_denied_events,
            "approval_events": approval_events,
            "session_rows": session_rows,
            "session_total_hint": Session.objects.filter(
                expire_date__gte=timezone.now()
            ).count(),
            "admin_security_audit_url": admin_security_audit_url,
            "admin_auditlog_url": admin_auditlog_url,
            "enterprise_super_http_audit": getattr(
                settings, "ENTERPRISE_SUPER_HTTP_AUDIT", False
            ),
            "verifier_cards": verifier_ctx["cards"],
            "governance_missing_files": verifier_ctx["missing_files"],
            "governance_risk_groups": verifier_ctx["risk_groups"],
            "route_audit_broken_count": verifier_ctx["route_broken_count"],
            "gilead_public_violations": verifier_ctx["gilead_public_violations"],
            "impersonation_rows": impersonation_rows,
            "security_surface_detail_url": surface_url,
        },
    )
