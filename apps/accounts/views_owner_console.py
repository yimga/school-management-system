"""Owner Console — slice 2: tenant-skinned console shell + Overview.

A first-class, tenant-scoped home for the school owner that unifies the surfaces
that already exist (the Tenant Identity hub, RBAC, billing, branding, audit) into
one coherent command center. It is:

* **Owner-gated** — only an actual owner (``SchoolMembership.is_school_owner``) or a
  platform superuser (support/recovery) may open it.
* **Tenant-skinned** — it extends ``portal_base.html`` (light + indigo), so it can
  never be mistaken for the operator's dark ``/super/`` plane, and it lives under
  the tenant urlconf (``/authentication/owner/``). No ``is_staff`` is involved.
* **Fail-soft** — every data read degrades to a safe default; the console never 500s.

Slice 2 shipped the Overview; slice 3 People & Roles; slice 4 the remaining
sections — Modules, Billing, Data, Branding and Audit — each as a bespoke console
sub-page that keeps the owner inside the shell and deep-links ("Open full …") into
the existing hub. Every section is owner-gated and fail-soft.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)


def is_school_owner(user, school) -> bool:
    """True when ``user`` may open the Owner Console for ``school``.

    Actual ownership only (the per-school ``is_school_owner`` flag); platform
    superusers are allowed for support/recovery. Deliberately does NOT admit the
    broad identity-hub manage roles — opening the owner's command center is an
    ownership-bearing act.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        from apps.schools.models import SchoolMembership

        return SchoolMembership.is_active_owner(user, school)
    except Exception as exc:  # noqa: BLE001 — fail closed
        logger.debug("owner console gate failed: %s", exc)
        return False


def _safe(name: str, *args) -> str | None:
    try:
        return reverse(name, args=args) if args else reverse(name)
    except NoReverseMatch:
        return None


def _console_sections(active: str) -> list[dict[str, Any]]:
    """The console left-nav: Overview + deep-links into existing hubs.

    Any section whose target URL doesn't resolve is dropped, so the nav never
    renders a dead link.
    """
    raw = [
        {"key": "overview", "label": _("Overview"), "icon": "bi-grid-1x2", "url": _safe("accounts:owner_console")},
        {"key": "people", "label": _("People & Roles"), "icon": "bi-people", "url": _safe("accounts:owner_console_people")},
        {"key": "rolegroups", "label": _("Role bundles"), "icon": "bi-collection", "url": _safe("accounts:owner_console_role_groups")},
        {"key": "rbac", "label": _("Roles & access"), "icon": "bi-shield-lock", "url": _safe("accounts:rbac")},
        {"key": "modules", "label": _("Modules"), "icon": "bi-puzzle", "url": _safe("accounts:owner_console_modules")},
        {"key": "billing", "label": _("Billing & plan"), "icon": "bi-credit-card", "url": _safe("accounts:owner_console_billing")},
        {"key": "data", "label": _("Data"), "icon": "bi-database", "url": _safe("accounts:owner_console_data")},
        {"key": "branding", "label": _("Branding"), "icon": "bi-palette", "url": _safe("accounts:owner_console_branding")},
        {"key": "audit", "label": _("Audit log"), "icon": "bi-journal-text", "url": _safe("accounts:owner_console_audit")},
    ]
    sections = []
    for item in raw:
        if not item["url"]:
            continue
        item["active"] = item["key"] == active
        sections.append(item)
    return sections


def _overview_metrics(school) -> dict[str, Any]:
    """People / owners / plan tiles + a small delegation sample. All fail-soft."""
    people_count = 0
    owner_rows: list[dict[str, Any]] = []
    delegation_rows: list[dict[str, Any]] = []
    try:
        from apps.schools.models import SchoolMembership

        base = SchoolMembership.objects.filter(school=school).select_related("user")
        people_count = base.count()
        owners = list(base.filter(is_school_owner=True)[:12])
        detail_url_name = "accounts:tenant_identity_detail"
        for m in owners:
            owner_rows.append(
                {
                    "name": (m.user.get_full_name() or m.user.get_username()),
                    "role": (m.role or "").replace("_", " ").title() or _("Admin"),
                    "url": _safe(detail_url_name, m.user_id),
                }
            )
        # A small "delegation at a glance" sample — non-owner members with a role.
        for m in base.filter(is_school_owner=False).order_by("-is_primary", "user__username")[:6]:
            delegation_rows.append(
                {
                    "name": (m.user.get_full_name() or m.user.get_username()),
                    "role": (m.role or "").replace("_", " ").title() or _("Member"),
                    "suspended": m.suspended_at is not None,
                    "url": _safe("accounts:tenant_identity_detail", m.user_id),
                }
            )
    except Exception as exc:  # noqa: BLE001 — tiles degrade to zeros, never 500
        logger.debug("owner console metrics failed: %s", exc)

    plan_label = ""
    try:
        plan_label = (getattr(school, "plan", "") or getattr(school, "billing_type", "") or "").replace("_", " ").title()
    except Exception:  # noqa: BLE001
        plan_label = ""

    return {
        "people_count": people_count,
        "owner_count": len(owner_rows),
        "owner_rows": owner_rows,
        "delegation_rows": delegation_rows,
        "plan_label": plan_label or _("Free"),
    }


@login_required
@require_school
def owner_console_overview(request):
    """The Owner Console Overview (owner-gated, tenant-skinned)."""
    school = request.school
    if not is_school_owner(request.user, school):
        return HttpResponseForbidden(
            _("The Owner Console is available to school owners.")
        )
    ctx = {
        "school": school,
        "owner_name": (request.user.get_full_name() or request.user.get_username()),
        "sections": _console_sections("overview"),
        "invite_url": _safe("accounts:tenant_identity_invite"),
        "roster_url": _safe("accounts:tenant_identity_roster"),
    }
    ctx.update(_overview_metrics(school))
    return render(request, "accounts/owner_console/overview.html", ctx)


# ── slice 4: section sub-pages (Modules / Billing / Data / Branding / Audit) ──


def _console_ctx(request, active: str) -> dict[str, Any]:
    """Shell context shared by every console page (nav + owner identity)."""
    school = request.school
    return {
        "school": school,
        "owner_name": (request.user.get_full_name() or request.user.get_username()),
        "sections": _console_sections(active),
        "invite_url": _safe("accounts:tenant_identity_invite"),
        "roster_url": _safe("accounts:tenant_identity_roster"),
    }


def _plan_label(school) -> str:
    """The school's plan/billing label, fail-soft, defaulting to Free."""
    try:
        label = (
            getattr(school, "plan", "") or getattr(school, "billing_type", "") or ""
        ).replace("_", " ").title()
    except Exception:  # noqa: BLE001
        label = ""
    return label or _("Free")


def _recent_audit_rows(school, limit: int = 10) -> list[dict[str, Any]]:
    """The most recent security/ownership events for this school. Fail-soft."""
    rows: list[dict[str, Any]] = []
    try:
        from apps.accounts.models import SecurityAuditLog

        qs = (
            SecurityAuditLog.objects.filter(school=school)
            .select_related("user")
            .order_by("-created_at")[:limit]
        )
        for e in qs:
            actor = ""
            if e.user_id:
                actor = e.user.get_full_name() or e.user.get_username()
            rows.append(
                {
                    "event": e.get_event_type_display(),
                    "actor": actor or _("System"),
                    "when": e.created_at,
                    "ip": e.ip_address or "",
                    "suspicious": bool(e.is_suspicious),
                }
            )
    except Exception as exc:  # noqa: BLE001 — the panel degrades to empty, never 500s
        logger.debug("owner console audit rows failed: %s", exc)
    return rows


def _owner_only(request, active: str):
    """Return (ctx, None) for an owner, or (None, 403 response) otherwise."""
    if not is_school_owner(request.user, request.school):
        return None, HttpResponseForbidden(
            _("The Owner Console is available to school owners.")
        )
    return _console_ctx(request, active), None


@login_required
@require_school
def owner_console_modules(request):
    """Modules — what's switched on for the school, deep-linking the Module Market."""
    ctx, denied = _owner_only(request, "modules")
    if denied:
        return denied
    ctx["module_market_url"] = _safe("siteconfig:module_market")
    ctx["grading_settings_url"] = _safe("siteconfig:grading_settings")
    return render(request, "accounts/owner_console/modules.html", ctx)


@login_required
@require_school
def owner_console_billing(request):
    """Billing & plan — plan at a glance, deep-linking the finance hub."""
    ctx, denied = _owner_only(request, "billing")
    if denied:
        return denied
    ctx["plan_label"] = _plan_label(request.school)
    ctx["billing_url"] = _safe("finance:dashboard")
    ctx["pricing_url"] = _safe("siteconfig:billing_plan_readonly")
    return render(request, "accounts/owner_console/billing.html", ctx)


@login_required
@require_school
def owner_console_data(request):
    """Data — import (Migration Cloud) and export (compliance) portability."""
    ctx, denied = _owner_only(request, "data")
    if denied:
        return denied
    ctx["import_url"] = _safe("accounts:migration_wizard")
    ctx["import_runs_url"] = _safe("accounts:migration_run_list")
    ctx["export_url"] = _safe("siteconfig:compliance_exports")
    return render(request, "accounts/owner_console/data.html", ctx)


@login_required
@require_school
def owner_console_branding(request):
    """Branding — the school's identity/theme, deep-linking the theme hubs."""
    ctx, denied = _owner_only(request, "branding")
    if denied:
        return denied
    ctx["theme_hub_url"] = _safe("siteconfig:theme_experience_hub")
    ctx["theme_colors_url"] = _safe("siteconfig:theme_colors")
    return render(request, "accounts/owner_console/branding.html", ctx)


@login_required
@require_school
def owner_console_audit(request):
    """Audit — recent security/ownership events, deep-linking the full log."""
    ctx, denied = _owner_only(request, "audit")
    if denied:
        return denied
    ctx["events"] = _recent_audit_rows(request.school)
    ctx["activity_log_url"] = _safe("accounts:tenant_activity_log")
    return render(request, "accounts/owner_console/audit.html", ctx)
