"""
System-wide action aggregation for dashboard next-action surfaces.

Aggregates lightweight, permission-aware suggestions from onboarding, tenant health,
role defaults, and operational signals. Does not replace domain-specific dashboard
builders; it adds a consistent cross-cutting strip so every dashboard exposes at
least one clear next step.

**Click / screen contract** (Phase 4 instrumentation):
- **Click**: primary-pointer activation on an actionable control (link, button,
  or chip with ``href`` / ``role="button"``) that advances or completes a task.
- **Screen**: distinct authenticated portal route load (full navigation), used as
  a coarse step boundary for ``data-task-step``.

Templates should set ``data-action="<domain>-<verb>"`` on actionable controls and
``data-task-step="<workflow>:<ordinal>"`` on multi-step flows for analytics.
See ``static/js/platform_behavior_track.js`` and ``apps.platform_runtime.click_tracking`` (measurement contract + medians).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from django.conf import settings
from django.urls import NoReverseMatch, reverse

_REVERSE_ERRORS = (NoReverseMatch, ValueError, TypeError)


def _safe_reverse(viewname: str, *args: Any, **kwargs: Any) -> Optional[str]:
    try:
        return reverse(viewname, args=args, kwargs=kwargs)
    except _REVERSE_ERRORS:
        return None


def _has_feature_permission(user, code: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    checker = getattr(user, "has_feature_permission", None)
    if not callable(checker) or not code:
        return False
    try:
        return bool(checker(code))
    except Exception:  # noqa: BLE001
        return False


def infer_primary_audience(user) -> str:
    """Coarse audience bucket for filtering suggestions (not authorization)."""
    if not user or not getattr(user, "is_authenticated", False):
        return "anonymous"
    role = (getattr(user, "role", "") or "").strip().upper()
    if role in {"TEACHER", "INSTRUCTOR"}:
        return "teacher"
    if role in {"PARENT", "GUARDIAN"}:
        return "parent"
    if role in {"STUDENT", "LEARNER"}:
        return "student"
    if role in {"OWNER", "FOUNDER", "PROPRIETOR", "LEADERSHIP"}:
        return "founder"
    if role in {"ADMIN", "PRINCIPAL", "HEAD"}:
        return "admin"
    if getattr(user, "is_staff", False):
        return "staff"
    return "all"


@dataclass(frozen=True)
class SystemAction:
    """One prioritized, navigable platform action (always has a URL — never bare stats)."""

    type: str
    title: str
    description: str
    action_url: str
    priority: int
    audience: str
    source: str
    urgency: str = "normal"  # low | normal | high | critical
    recommendation_key: str = ""  # set when sourced from ai_recommendation_registry


def _conversion_action_tier(action: SystemAction) -> int:
    """
    Strip ordering when CONVERSION_SINGLE_ACTION_ENFORCED is on:
    onboarding → health → revenue → optimization (everything else).
    """
    t = (action.type or "").lower()
    src = (action.source or "").lower()
    if t == "onboarding" or src == "onboarding_steps":
        return 0
    if t == "system_health" or src in ("customer_health", "siteconfig"):
        return 1
    if t in ("payments", "marketplace") or src in ("finance", "marketplace"):
        return 2
    return 3


def _dedupe(actions: Iterable[SystemAction]) -> list[SystemAction]:
    seen: set[tuple[str, str]] = set()
    out: list[SystemAction] = []
    for a in actions:
        key = (a.title.strip().lower(), a.action_url)
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _operator_audience_for_bucket(bucket: str) -> str:
    if bucket in {"founder", "admin", "staff"}:
        return "admin"
    return bucket


def _first_resolved_url(viewnames: Sequence[str]) -> Optional[str]:
    for vn in viewnames:
        u = _safe_reverse(vn)
        if u:
            return u
    return None


def _registry_audience_allows(aud_set: set[str], bucket: str) -> bool:
    if not aud_set:
        return False
    if "all" in aud_set:
        return True
    if bucket in aud_set:
        return True
    if bucket in {"founder", "admin", "staff"} and (
        "operator" in aud_set or "admin" in aud_set
    ):
        return True
    return False


def _collect_ai_registry_actions(user, school: Any, bucket: str) -> list[SystemAction]:
    """
    Map ``ai_recommendation_registry`` generators to real ``SystemAction`` rows.

    Skips entries with no resolvable URL or empty generator output (no dead suggestions).
    """
    if school is None:
        return []
    try:
        from apps.platform_runtime.ai_recommendation_registry import (
            AI_RECOMMENDATION_REGISTRY,
        )
    except Exception:  # noqa: BLE001
        return []

    out: list[SystemAction] = []
    op_aud = _operator_audience_for_bucket(bucket)

    for key, meta in AI_RECOMMENDATION_REGISTRY.items():
        raw_aud = meta.get("audiences") or ()
        aud_set = {str(x).lower() for x in raw_aud} if raw_aud else set()
        if not _registry_audience_allows(aud_set, bucket):
            continue

        chains = meta.get("action_url_chains") or {}
        if bucket in {"founder", "admin", "staff"}:
            chain = chains.get("operator") or chains.get("default") or ()
        else:
            chain = chains.get(bucket) or chains.get("default") or ()
        if not chain:
            chain = meta.get("url_fallback_views") or ()
        url = _first_resolved_url(tuple(chain))
        if not url:
            continue

        gen = meta.get("generator")
        if not callable(gen):
            continue

        try:
            if key == "workflow_hygiene":
                rec = gen(school, user, str(meta.get("workflow_signal_key") or "platform_strip"))
            elif key == "anomaly_risk":
                rec = gen(school, user)
                if rec is None:
                    continue
            else:
                rec = gen(school, user)
        except Exception:  # noqa: BLE001
            continue

        if not isinstance(rec, dict):
            continue
        title = (rec.get("title") or meta.get("title") or key).strip()
        expl = (rec.get("explanation") or "").strip()
        prop = (rec.get("proposed_action") or "").strip()
        desc = expl
        if prop:
            desc = f"{expl} {prop}".strip()[:400]
        if not title or not desc:
            continue

        cat = str(meta.get("category") or "ai")
        priority = int(meta.get("priority") or 74)
        urg = str(meta.get("urgency") or "normal")
        src = f"ai_registry:{key}"
        aud = op_aud if bucket in {"founder", "admin", "staff"} else bucket

        out.append(
            SystemAction(
                type=f"ai_{cat}",
                title=title[:200],
                description=desc[:500],
                action_url=url,
                priority=priority,
                audience=aud,
                source=src,
                urgency=urg if urg in {"low", "normal", "high", "critical"} else "normal",
                recommendation_key=key[:120],
            )
        )
    return out


def _collect_onboarding(school: Any, audience: str) -> list[SystemAction]:
    if school is None:
        return []
    try:
        from apps.platform_runtime.customer_health import get_school_health_recommendations

        rows = get_school_health_recommendations(school, limit=6)
    except Exception:  # noqa: BLE001
        return []
    out: list[SystemAction] = []
    for i, row in enumerate(rows):
        url = (row.get("url") or "").strip()
        label = (row.get("label") or "Next step").strip()
        if not url:
            continue
        out.append(
            SystemAction(
                type="onboarding",
                title=label,
                description="Complete setup to unlock full value.",
                action_url=url,
                priority=95 - min(i, 5),
                audience="all",
                source="onboarding_steps",
            )
        )
    return out


def _collect_health(school: Any, audience: str) -> list[SystemAction]:
    if school is None:
        return []
    try:
        from apps.platform_runtime.customer_health import calculate_school_health

        h = calculate_school_health(school)
        status = str(h.get("status") or "")
    except Exception:  # noqa: BLE001
        return []
    url = _safe_reverse("siteconfig:dashboard_hub") or _safe_reverse("accounts:backend_dashboard")
    if status == "setup_needed" and url:
        return [
            SystemAction(
                type="system_health",
                title="Finish school activation",
                description="Continue guided setup so teams can operate with confidence.",
                action_url=url,
                priority=70,
                audience="all",
                source="customer_health",
            )
        ]
    if status == "at_risk" and url:
        return [
            SystemAction(
                type="system_health",
                title="Deepen usage",
                description="Reports or roster depth look light — one focused session improves outcomes.",
                action_url=url,
                priority=55,
                audience="all",
                source="customer_health",
            )
        ]
    return []


def _collect_teacher_actions(user, school: Any) -> list[SystemAction]:
    out: list[SystemAction] = []
    marks = _safe_reverse("evals:teacher_marks_entry")
    if marks:
        out.append(
            SystemAction(
                type="academics",
                title="Marks & grading",
                description="Enter or review marks without leaving your flow.",
                action_url=marks,
                priority=40,
                audience="teacher",
                source="role_default",
            )
        )
    att = _safe_reverse("portal:teacher_attendance")
    if att:
        out.append(
            SystemAction(
                type="attendance",
                title="Attendance",
                description="Capture attendance while context is fresh.",
                action_url=att,
                priority=38,
                audience="teacher",
                source="role_default",
            )
        )
    return out


def _collect_student_actions(user, school: Any) -> list[SystemAction]:
    """Learner defaults — always navigable URLs (Phase: controlled platform)."""
    out: list[SystemAction] = []
    home = _safe_reverse("portal:student_portal_grades")
    if home:
        out.append(
            SystemAction(
                type="learning",
                title="Learning home",
                description="Grades, tasks, and your operating surface.",
                action_url=home,
                priority=42,
                audience="student",
                source="role_default",
            )
        )
    onboard = _safe_reverse("portal:student_onboarding")
    if onboard:
        out.append(
            SystemAction(
                type="onboarding",
                title="Student onboarding",
                description="Finish setup so your portal reflects your profile.",
                action_url=onboard,
                priority=36,
                audience="student",
                source="role_default",
            )
        )
    sup = _safe_reverse("feedback:help_center")
    if sup:
        out.append(
            SystemAction(
                type="support",
                title="Help & support",
                description="Get unstuck without leaving the portal.",
                action_url=sup,
                priority=24,
                audience="student",
                source="role_default",
            )
        )
    return out


def _fallback_minimum_actions(user, school: Any, bucket: str) -> list[SystemAction]:
    """
    Guarantee at least one actionable chip when no signals fired — eliminates dead-end strips.
    """
    rows: list[SystemAction] = []
    if bucket == "student":
        u = _safe_reverse("portal:student_portal_grades")
        if u:
            rows.append(
                SystemAction(
                    type="navigation",
                    title="Open your portal",
                    description="Continue where you left off.",
                    action_url=u,
                    priority=10,
                    audience="student",
                    source="fallback_minimum",
                )
            )
    elif bucket == "parent":
        u = _safe_reverse("portal:parent_dashboard")
        if u:
            rows.append(
                SystemAction(
                    type="navigation",
                    title="Family home",
                    description="Fees, updates, and learner progress.",
                    action_url=u,
                    priority=10,
                    audience="parent",
                    source="fallback_minimum",
                )
            )
    elif bucket == "teacher":
        u = _safe_reverse("evals:teacher_marks_entry") or _safe_reverse(
            "portal:teacher_attendance"
        )
        if u:
            rows.append(
                SystemAction(
                    type="navigation",
                    title="Teaching workspace",
                    description="Marks or attendance — pick up operational work.",
                    action_url=u,
                    priority=10,
                    audience="teacher",
                    source="fallback_minimum",
                )
            )
    elif bucket in {"admin", "founder", "staff", "all"}:
        u = _safe_reverse("accounts:backend_dashboard") or _safe_reverse(
            "siteconfig:dashboard_hub"
        )
        if u:
            rows.append(
                SystemAction(
                    type="navigation",
                    title="Operations home",
                    description="School controls and live operational surfaces.",
                    action_url=u,
                    priority=10,
                    audience=bucket if bucket != "all" else "admin",
                    source="fallback_minimum",
                )
            )
    help_u = _safe_reverse("feedback:help_center") or _safe_reverse(
        "portal:support_request"
    )
    if help_u and len(rows) < 3:
        rows.append(
            SystemAction(
                type="support",
                title="Help center",
                description="Guidance when you are unsure what to do next.",
                action_url=help_u,
                priority=5,
                audience="all",
                source="fallback_minimum",
            )
        )
    return rows


def _collect_parent_actions(user, school: Any) -> list[SystemAction]:
    out: list[SystemAction] = []
    try:
        from decimal import Decimal

        from apps.finance.family_billing_aggregator import aggregate_family_balance

        summary = aggregate_family_balance(guardian_user_id=int(user.pk))
        open_bal = summary.family_total_open_balance
        if open_bal and open_bal > Decimal("0"):
            pay_all = _safe_reverse("portal:parent_finance_pay_all")
            if pay_all and not summary.currency_mismatch:
                out.append(
                    SystemAction(
                        type="payments",
                        title="Pay family balance",
                        description="One checkout for every linked learner.",
                        action_url=pay_all,
                        priority=88,
                        audience="parent",
                        urgency="high",
                        source="family_billing",
                    )
                )
    except Exception:  # noqa: BLE001
        pass
    dash = _safe_reverse("portal:parent_dashboard")
    if dash:
        out.append(
            SystemAction(
                type="reports",
                title="Family home",
                description="Fees, notices, and learner progress in one calm view.",
                action_url=dash,
                priority=35,
                audience="parent",
                source="role_default",
            )
        )
    fin = _safe_reverse("portal:parent_finance")
    if fin:
        out.append(
            SystemAction(
                type="payments",
                title="Fees & invoices",
                description="Balances, receipts, and payment history.",
                action_url=fin,
                priority=32,
                audience="parent",
                source="role_default",
            )
        )
    comm = _safe_reverse("portal:parent_feed") or _safe_reverse("portal:parent_contact_school")
    if comm:
        out.append(
            SystemAction(
                type="reports",
                title="School updates",
                description="Notices and school updates in one calm feed.",
                action_url=comm,
                priority=30,
                audience="parent",
                source="role_default",
            )
        )
    return out


def _collect_marketplace_actions(user, school: Any) -> list[SystemAction]:
    """Install / extend capability — one tap into module catalog."""
    url = _safe_reverse("siteconfig:module_market")
    if not url or not (
        getattr(user, "is_staff", False)
        or _has_feature_permission(user, "settings.manage")
        or _has_feature_permission(user, "marketplace.view")
    ):
        return []
    return [
        SystemAction(
            type="marketplace",
            title="Modules & extensions",
            description="Enable or adjust capabilities without hunting menus.",
            action_url=url,
            priority=25,
            audience="admin",
            urgency="normal",
            source="marketplace",
        )
    ]


def _collect_operator_actions(user, school: Any) -> list[SystemAction]:
    """Admin / founder / staff — operations and trust surfaces."""
    out: list[SystemAction] = []
    fin = _safe_reverse("finance:dashboard")
    if fin and (
        _has_feature_permission(user, "finance.view_dashboard")
        or _has_feature_permission(user, "finance.access")
        or getattr(user, "is_staff", False)
    ):
        out.append(
            SystemAction(
                type="payments",
                title="Finance pulse",
                description="Cash, invoices, and compliance in one place.",
                action_url=fin,
                priority=45,
                audience="admin",
                source="finance",
            )
        )
    rep = _safe_reverse("analytics:dashboard") or _safe_reverse("emis:dashboard")
    if rep and (_has_feature_permission(user, "reports.view") or getattr(user, "is_staff", False)):
        out.append(
            SystemAction(
                type="reports",
                title="Reports & insight",
                description="Answers without exporting spreadsheets.",
                action_url=rep,
                priority=33,
                audience="admin",
                source="reports",
            )
        )
    sec = _safe_reverse("compliance:dashboard")
    if sec and getattr(user, "is_staff", False):
        out.append(
            SystemAction(
                type="security",
                title="Compliance & audit",
                description="Review obligations before they become incidents.",
                action_url=sec,
                priority=28,
                audience="admin",
                source="compliance",
            )
        )
    hub = _safe_reverse("siteconfig:dashboard_hub")
    if hub:
        out.append(
            SystemAction(
                type="system_health",
                title="Configuration hub",
                description="Tenant controls with safe defaults.",
                action_url=hub,
                priority=22,
                audience="founder",
                source="siteconfig",
            )
        )
    return out


def _audience_matches(action: SystemAction, bucket: str) -> bool:
    if action.audience == "all":
        return True
    if bucket in {"founder", "admin", "staff"} and action.audience in {
        "admin",
        "founder",
        "staff",
    }:
        return True
    return action.audience == bucket


def get_control_plane_actions(
    user,
    *,
    limit: int = 6,
    request: Any | None = None,
) -> list[SystemAction]:
    """
    When no tenant ``school`` is on the request (e.g. control plane / super routes),
    surface operational next steps — not generic "open the page you are already on".
    """
    if not user or not getattr(user, "is_authenticated", False):
        return []
    if not (
        getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
    ):
        return []
    current_path = ""
    if request is not None:
        current_path = (getattr(request, "path", "") or "").split("?", 1)[0].rstrip("/")

    out: list[SystemAction] = []
    pairs: list[tuple[str, str, str, int]] = [
        (
            "super:schools_list",
            "School directory",
            "Query tenants, open Tenant 360, and run lifecycle actions.",
            90,
        ),
        (
            "super:tenant_health",
            "Tenant health grid",
            "Review health, onboarding stage, and schools needing attention.",
            85,
        ),
        (
            "super:command_center",
            "Operational queues",
            "Support backlog, provisioning SLA breaches, and approvals.",
            80,
        ),
        (
            "super:offboarding_queue",
            "Offboarding queue",
            "Wind-down, export, and scheduled purge workflows.",
            75,
        ),
        (
            "super:dashboard",
            "Control plane home",
            "Portfolio pulse, globe footprint, and tenant heatmap.",
            60,
        ),
        (
            "super:founder_dashboard",
            "Founder metrics",
            "Platform closure metrics and audit posture.",
            55,
        ),
        (
            "siteconfig:console_domains_hub",
            "Configuration center",
            "Domains, DNS, and platform wiring.",
            50,
        ),
    ]
    for viewname, title, desc, priority in pairs:
        url = _safe_reverse(viewname)
        if not url:
            continue
        normalized = url.rstrip("/")
        if current_path and normalized == current_path:
            continue
        out.append(
            SystemAction(
                type="system_health",
                title=title,
                description=desc,
                action_url=url,
                priority=priority,
                audience="founder",
                source="control_plane",
            )
        )
    out.sort(key=lambda a: (-a.priority, a.title.lower()))
    return out[:limit]


def get_actions_for_user(
    user,
    school: Any | None = None,
    *,
    request: Any | None = None,
    limit: int = 6,
) -> list[SystemAction]:
    """
    Return prioritized actions for the current user and tenant.

    Pass ``request`` so ``request.school`` is used when ``school`` is omitted.
    Permission-sensitive URLs are only emitted when a coarse permission check passes;
    authorization remains enforced by views.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return []
    if school is None and request is not None:
        school = getattr(request, "school", None)
    if school is None:
        # Control-plane surfaces live under /super/ and have no tenant school.
        path = ""
        if request is not None:
            path = getattr(request, "path", "") or ""
        if path.startswith("/super/"):
            return get_control_plane_actions(user, limit=limit, request=request)
        return []

    bucket = infer_primary_audience(user)
    merged: list[SystemAction] = []

    merged.extend(_collect_onboarding(school, bucket))
    merged.extend(_collect_health(school, bucket))
    merged.extend(_collect_ai_registry_actions(user, school, bucket))

    if bucket == "teacher":
        merged.extend(_collect_teacher_actions(user, school))
    elif bucket == "parent":
        merged.extend(_collect_parent_actions(user, school))
    elif bucket == "student":
        merged.extend(_collect_student_actions(user, school))
    elif bucket in {"admin", "founder", "staff", "all"}:
        merged.extend(_collect_operator_actions(user, school))
        merged.extend(_collect_marketplace_actions(user, school))
        if bucket == "staff":
            merged.extend(_collect_teacher_actions(user, school))

    merged = [a for a in merged if _audience_matches(a, bucket)]
    merged = _dedupe(merged)
    if not merged:
        merged = _fallback_minimum_actions(user, school, bucket)
    single = getattr(settings, "CONVERSION_SINGLE_ACTION_ENFORCED", False)
    if single:
        merged.sort(
            key=lambda a: (
                _conversion_action_tier(a),
                -a.priority,
                a.title.lower(),
            )
        )
    else:
        merged.sort(key=lambda a: (-a.priority, a.title.lower()))
    cap = 1 if single else max(1, min(limit, 12))
    return merged[:cap]


def serialize_actions(actions: Sequence[SystemAction]) -> list[dict[str, Any]]:
    """Template- and JSON-friendly dicts."""
    return [
        {
            "type": a.type,
            "title": a.title,
            "description": a.description,
            "action_url": a.action_url,
            "priority": a.priority,
            "audience": a.audience,
            "source": a.source,
            "urgency": getattr(a, "urgency", None) or "normal",
            "recommendation_key": getattr(a, "recommendation_key", "") or "",
            "task_code": (
                f"ai:{(getattr(a, 'recommendation_key', '') or '').strip()}"
                if (getattr(a, "recommendation_key", "") or "").strip()
                else ""
            ),
        }
        for a in actions
    ]
