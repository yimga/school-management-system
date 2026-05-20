"""
Unified manager /admin/ steering strip — path hints, outcome deck, changelist CP hints.
"""

from __future__ import annotations

import re
from typing import Any

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

_CHANGE_LIST_PATH = re.compile(r"^/admin/([^/]+)/([^/]+)/?$")

# App-level changelist hints (formerly per-app change_list.html <details> blocks).
_PLATFORM_CHANGESET_HINTS: dict[str, dict[str, Any]] = {
    "siteconfig": {
        "title": _("Control plane first"),
        "body": _(
            "Fleet and system configuration are integrated in the control plane "
            "(/super/) and the Configuration Control Center. Use this Django changelist "
            "only for deep maintenance or fields not yet exposed in super."
        ),
        "links": (
            ("super:platform_operator_hub", _("Platform operator hub")),
            ("siteconfig:console_domains_hub", _("Config center")),
            ("super:dashboard", _("Control plane dashboard")),
        ),
    },
    "global_registries": {
        "title": _("Control plane first"),
        "body": _(
            "Global registry catalog work (regions, education systems, geography) is "
            "available in the control plane. Use this changelist for deep maintenance only."
        ),
        "links": (
            ("super:regions_list", _("Regions (super)")),
            ("super:education_systems", _("Education systems (super)")),
            ("super:geography", _("Geography (super)")),
        ),
    },
    "integrations_marketplace": {
        "title": _("Integrations & marketplace"),
        "body": _(
            "Integration catalog governance and publisher apps are managed from the "
            "control plane first. Use this changelist for credential rows and deep fixes."
        ),
        "links": (
            ("super:marketplace_governance", _("Marketplace governance")),
            ("super:platform_operator_hub", _("Operator hub")),
            ("siteconfig:console_domains_hub", _("Config center")),
        ),
    },
    "marketplace": {
        "title": _("Marketplace records"),
        "body": _(
            "Publisher listings and install health live under Marketplace governance. "
            "Use admin for break-glass publisher record edits."
        ),
        "links": (
            ("super:marketplace_governance", _("Marketplace governance")),
            ("super:blueprint_marketplace", _("Blueprint marketplace")),
        ),
    },
    "billing": {
        "title": _("Billing & revenue"),
        "body": _(
            "Fleet billing accounts and revenue operations are surfaced on the control "
            "plane. Use admin changelists for ledger-grade row maintenance."
        ),
        "links": (
            ("super:billing_accounts_list", _("Billing accounts (super)")),
            ("super:dashboard", _("Control plane")),
        ),
    },
}


def _rev(url_name: str) -> str | None:
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def build_admin_steering_hint(
    request, *, is_platform_site: bool
) -> dict[str, Any] | None:
    """Changelist-only app hints merged into the unified steering strip."""
    if not is_platform_site:
        return None
    path = (getattr(request, "path", "") or "").lower().rstrip("/") or "/"
    match = _CHANGE_LIST_PATH.match(path)
    if not match:
        return None
    app_label = match.group(1)
    spec = _PLATFORM_CHANGESET_HINTS.get(app_label)
    if not spec:
        return None
    links: list[dict[str, str]] = []
    for url_name, label in spec.get("links") or ():
        url = _rev(url_name)
        if url:
            links.append({"label": str(label), "url": url})
    if not links:
        return None
    return {
        "hint_id": app_label,
        "title": str(spec.get("title", "")),
        "body": str(spec.get("body", "")),
        "links": links,
    }


def build_admin_index_kpi_strip(dashboard_context: dict[str, Any]) -> list[dict[str, Any]]:
    """Compact KPI row for platform admin index from build_admin_dashboard_context."""
    items: list[dict[str, Any]] = []

    def _add(kpi_id: str, label: str, value: Any, *, url_name: str | None = None) -> None:
        entry: dict[str, Any] = {
            "id": kpi_id,
            "label": label,
            "value": value,
        }
        if url_name:
            entry["url"] = _rev(url_name)
        items.append(entry)

    if dashboard_context.get("can_see_user_stats"):
        _add("users", _("Users"), dashboard_context.get("total_users", 0))
        _add("staff", _("Staff"), dashboard_context.get("admin_count", 0))
    if dashboard_context.get("can_see_sessions"):
        _add("sessions", _("Active sessions"), dashboard_context.get("active_sessions", 0))
        _add(
            "sessions_24h",
            _("Sessions (24h)"),
            dashboard_context.get("sessions_24h", 0),
        )
    if dashboard_context.get("can_see_compliance"):
        _add(
            "security_alerts",
            _("Security alerts (24h)"),
            dashboard_context.get("security_alerts_24h", 0),
        )
        _add(
            "access_denials",
            _("Access denials (24h)"),
            dashboard_context.get("access_denials_24h", 0),
        )
    pending = dashboard_context.get("pending_approvals_count", 0)
    if pending:
        _add("pending_approvals", _("Pending approvals"), pending)
    _add("logins_24h", _("New logins (24h)"), dashboard_context.get("new_logins_24h", 0))
    _add(
        "failed_logins",
        _("Failed logins (24h)"),
        dashboard_context.get("failed_logins_24h", 0),
    )
    _add("system_health", _("System"), _("Operational"), url_name="admin:system_health")
    return items
