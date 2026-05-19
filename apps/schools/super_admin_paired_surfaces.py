# -*- coding: utf-8 -*-
"""
Operator IA spine: /super/, /configuration/, and /admin/ stay separate products but
share cross-links and audit metadata.

See docs/CONTROL_PLANE_AND_PLATFORM_ADMIN.md and batch 1252 surface parity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.schools.super_admin_bridge_registry import PLATFORM_ADMIN_BRIDGES


@dataclass(frozen=True)
class OperatorSurfaceLink:
    """One navigable surface in the operator spine or a paired row."""

    link_id: str
    label: str
    url: str
    surface: str  # super | configuration | admin | policy
    active: bool = False
    description: str = ""
    icon: str = ""


# Always-on spine (manager host). Order is intentional for the workspace nav UI.
# Tuple: surface, url_name, label, bootstrap-icons class.
OPERATOR_SURFACE_SPINE_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("super", "super:dashboard", _("Control plane"), "bi-speedometer2"),
    ("super", "super:platform_operator_hub", _("Operator hub"), "bi-compass"),
    ("configuration", "configuration:center", _("Config center"), "bi-gear-wide-connected"),
    ("admin", "admin:index", _("Platform admin"), "bi-building-gear"),
    ("super", "super:operator_policy", _("Policies"), "bi-shield-check"),
)

# Super-first flows with optional break-glass admin bridge.
SUPER_FIRST_PAIRED_SPECS: tuple[dict[str, str], ...] = (
    {
        "slug": "schools",
        "label": _("Schools"),
        "super_url_name": "super:schools_list",
        "bridge_key": "schools_school",
    },
    {
        "slug": "site_settings",
        "label": _("Site settings"),
        "super_url_name": "super:site_settings_list",
        "bridge_key": "",
    },
    {
        "slug": "regions",
        "label": _("Regions"),
        "super_url_name": "super:regions_list",
        "bridge_key": "",
    },
    {
        "slug": "grading",
        "label": _("Grading scales"),
        "super_url_name": "super:grading_list",
        "bridge_key": "",
    },
    {
        "slug": "plans",
        "label": _("Plans & add-ons"),
        "super_url_name": "super:plans_list",
        "bridge_key": "",
    },
    {
        "slug": "feature_toggles",
        "label": _("Feature toggles"),
        "super_url_name": "super:feature_toggles_list",
        "bridge_key": "feature_toggle_states",
    },
    {
        "slug": "incidents",
        "label": _("Incidents"),
        "super_url_name": "super:incidents_list",
        "bridge_key": "platform_incidents_admin",
    },
    {
        "slug": "billing_accounts",
        "label": _("Billing accounts"),
        "super_url_name": "super:billing_accounts_list",
        "bridge_key": "billing_billingaccount",
    },
    {
        "slug": "migration_runs",
        "label": _("Migration runs"),
        "super_url_name": "super:migration_runs_list",
        "bridge_key": "migration_runs_admin",
    },
    {
        "slug": "integrations",
        "label": _("Integrations"),
        "super_url_name": "",
        "bridge_key": "integrations",
    },
    {
        "slug": "marketplace_governance",
        "label": _("Marketplace governance"),
        "super_url_name": "super:marketplace_governance",
        "bridge_key": "marketplace_apps",
    },
    {
        "slug": "security_hub",
        "label": _("Security hub"),
        "super_url_name": "super:security_hub",
        "bridge_key": "compliance_audit_log",
    },
    {
        "slug": "trust_center",
        "label": _("Trust center"),
        "super_url_name": "super:trust_center",
        "bridge_key": "platform_event_logs",
    },
    {
        "slug": "runtime_defaults",
        "label": _("Runtime defaults"),
        "super_url_name": "",
        "bridge_key": "runtime_defaults",
    },
    {
        "slug": "fleet_governed_changes",
        "label": _("Fleet governed changes"),
        "super_url_name": "super:fleet_governed_changes",
        "bridge_key": "fleet_governed_changes",
    },
    {
        "slug": "ai_model_hub",
        "label": _("AI model hub"),
        "super_url_name": "super:ai_model_hub",
        "bridge_key": "ai_model_registry",
    },
)

# Super views that should show a break-glass admin bridge chip (exact url_name).
SUPER_VIEW_BRIDGE_BINDINGS: dict[str, str] = {
    "marketplace_governance": "marketplace_apps",
    "blueprint_marketplace": "marketplace_listings",
    "app_catalog": "marketplace_apps",
    "marketplace_incident_dashboard": "platform_incidents_admin",
    "marketplace_compatibility": "marketplace_apps",
    "marketplace_installation_health": "marketplace_apps",
    "marketplace_sandbox_inspector": "marketplace_apps",
    "security_hub": "compliance_audit_log",
    "security_command_center": "compliance_audit_log",
    "enterprise_security_command_center": "compliance_audit_log",
    "security_surface_dashboard": "compliance_audit_log",
    "trust_center": "platform_event_logs",
}

# Nested /super/... routes inherit the nearest prefix bridge (longest match wins).
SUPER_PATH_PREFIX_BRIDGE_BINDINGS: tuple[tuple[str, str], ...] = (
    ("/super/marketplace/", "marketplace_apps"),
    ("/super/security/", "compliance_audit_log"),
    ("/super/trust/", "platform_event_logs"),
)

# Playwright / smoke probes (manager host, authenticated superuser).
MANAGER_BROWSER_PARITY_PROBES: tuple[dict[str, Any], ...] = (
    {
        "slug": "super_dashboard",
        "path_name": "super:dashboard",
        "expect_strip": True,
        "expect_paired": False,
    },
    {
        "slug": "super_schools",
        "path_name": "super:schools_list",
        "expect_strip": True,
        "expect_paired": True,
    },
    {
        "slug": "super_marketplace",
        "path_name": "super:marketplace_governance",
        "expect_strip": True,
        "expect_paired": True,
    },
    {
        "slug": "super_security",
        "path_name": "super:security_hub",
        "expect_strip": True,
        "expect_paired": True,
    },
    {
        "slug": "configuration_center",
        "path_name": "configuration:center",
        "expect_strip": True,
        "expect_paired": False,
    },
    {
        "slug": "admin_index",
        "path_name": "admin:index",
        "expect_strip": True,
        "expect_paired": False,
    },
    {
        "slug": "admin_schools",
        "path_name": "admin:schools_school_changelist",
        "expect_strip": True,
        "expect_paired": True,
        "paired_operator": True,
    },
    {
        "slug": "admin_marketplace_apps",
        "path_name": "admin:integrations_marketplace_marketplaceapp_changelist",
        "expect_strip": True,
        "expect_paired": True,
        "paired_operator": True,
    },
    {
        "slug": "admin_compliance_audit",
        "path_name": "admin:compliance_auditlog_changelist",
        "expect_strip": True,
        "expect_paired": True,
        "paired_operator": True,
    },
)


def _is_manager_operator_host(request) -> bool:
    kind = (getattr(request, "public_host_kind", None) or "").lower()
    return kind in {"manager", "local", ""}


def _operator_surface_strip_visible(request) -> bool:
    """Workspace nav renders on /super/ and /configuration/, not Django admin."""
    path = (getattr(request, "path", None) or "").lower().rstrip("/") or "/"
    if path == "/admin" or path.startswith("/admin/"):
        return False
    if path == "/internal-admin" or path.startswith("/internal-admin/"):
        return False
    return True


def _detect_operator_surface(request) -> str | None:
    path = (getattr(request, "path", None) or "").lower()
    if path.startswith("/super/"):
        return "super"
    if path.startswith("/configuration/"):
        return "configuration"
    if path.startswith("/admin/") or path.startswith("/internal-admin/"):
        return "admin"
    return None


def _safe_reverse(url_name: str, kwargs: dict | None = None) -> str | None:
    try:
        return reverse(url_name, kwargs=kwargs or {})
    except NoReverseMatch:
        return None


def bridge_key_for_admin_url_name(admin_url_name: str) -> str | None:
    for key, meta in PLATFORM_ADMIN_BRIDGES.items():
        if str(meta.get("admin_url")) == admin_url_name:
            return key
    return None


def bridge_key_for_request(request) -> str | None:
    match = getattr(request, "resolver_match", None)
    if not match or not match.url_name:
        return None
    app_name = getattr(match, "app_name", None) or ""
    if app_name != "admin":
        return None
    admin_url_name = f"admin:{match.url_name}"
    if not admin_url_name.endswith("_changelist"):
        return None
    return bridge_key_for_admin_url_name(admin_url_name)


def super_first_spec_for_url_name(url_name: str) -> dict[str, str] | None:
    for spec in SUPER_FIRST_PAIRED_SPECS:
        if spec.get("super_url_name") == url_name:
            return spec
    return None


def super_first_spec_for_bridge_key(bridge_key: str) -> dict[str, str] | None:
    preferred: dict[str, str] | None = None
    for spec in SUPER_FIRST_PAIRED_SPECS:
        if spec.get("bridge_key") != bridge_key:
            continue
        if (spec.get("super_url_name") or "").strip():
            return spec
        if preferred is None:
            preferred = spec
    return preferred


def resolve_bridge_key_for_super_view(
    url_name: str, path: str | None = None
) -> str | None:
    """Map a super view (and optional path) to a platform-admin bridge key."""
    if not url_name:
        return None
    full_name = f"super:{url_name}"
    spec = super_first_spec_for_url_name(full_name)
    if spec:
        bridge_key = (spec.get("bridge_key") or "").strip()
        if bridge_key:
            return bridge_key
    bound = SUPER_VIEW_BRIDGE_BINDINGS.get(url_name)
    if bound:
        return bound
    normalized = (path or "").lower()
    if normalized:
        best_len = -1
        best_key: str | None = None
        for prefix, bridge_key in SUPER_PATH_PREFIX_BRIDGE_BINDINGS:
            if normalized.startswith(prefix) and len(prefix) > best_len:
                best_len = len(prefix)
                best_key = bridge_key
        if best_key:
            return best_key
    return None


def _append_admin_bridge_link(
    links: list[OperatorSurfaceLink], bridge_key: str
) -> None:
    admin_bridge_url = _safe_reverse(
        "super:admin_bridge", kwargs={"bridge_key": bridge_key}
    )
    if not admin_bridge_url:
        return
    meta = PLATFORM_ADMIN_BRIDGES.get(bridge_key) or {}
    links.append(
        OperatorSurfaceLink(
            link_id=f"admin_bridge_{bridge_key}",
            label=_("Open platform admin"),
            url=admin_bridge_url,
            surface="admin",
            description=str(meta.get("description", "")),
            icon="bi-box-arrow-in-right",
        )
    )


def build_operator_surface_spine(request) -> list[OperatorSurfaceLink]:
    current = _detect_operator_surface(request)
    links: list[OperatorSurfaceLink] = []
    for surface, url_name, label, icon in OPERATOR_SURFACE_SPINE_SPECS:
        url = _safe_reverse(url_name)
        if not url:
            continue
        links.append(
            OperatorSurfaceLink(
                link_id=url_name.replace(":", "_"),
                label=str(label),
                url=url,
                surface=surface,
                active=current == surface,
                icon=icon,
            )
        )
    return links


def build_paired_surface_links(request) -> list[OperatorSurfaceLink]:
    """Contextual super ↔ admin pair for the current changelist or super list."""
    match = getattr(request, "resolver_match", None)
    if not match:
        return []

    links: list[OperatorSurfaceLink] = []
    namespace = getattr(match, "app_name", None) or ""
    url_name = getattr(match, "url_name", None) or ""

    if namespace == "super" and url_name:
        bridge_key = resolve_bridge_key_for_super_view(
            url_name, getattr(request, "path", None)
        )
        if bridge_key:
            _append_admin_bridge_link(links, bridge_key)

    if namespace == "admin" and url_name:
        bridge_key = bridge_key_for_admin_url_name(f"admin:{url_name}")
        if bridge_key:
            spec = super_first_spec_for_bridge_key(bridge_key)
            super_url_name = (spec or {}).get("super_url_name", "").strip()
            if super_url_name:
                super_url = _safe_reverse(super_url_name)
                if super_url:
                    links.append(
                        OperatorSurfaceLink(
                            link_id=f"super_{spec.get('slug', bridge_key)}",
                            label=_("Open operator view"),
                            url=super_url,
                            surface="super",
                            description=_(
                                "Super-first control plane list for this domain."
                            ),
                            icon="bi-arrow-left-right",
                        )
                    )
            else:
                hub_url = _safe_reverse("super:platform_operator_hub")
                if hub_url:
                    links.append(
                        OperatorSurfaceLink(
                            link_id="operator_hub",
                            label=_("Operator hub"),
                            url=hub_url,
                            surface="super",
                            description=_(
                                "Curated operator directory for this admin model."
                            ),
                            icon="bi-compass",
                        )
                    )

    return links


def build_operator_surface_ia_context(request) -> dict[str, Any]:
    if not _is_manager_operator_host(request):
        return {
            "RMC_OPERATOR_SURFACE_IA": False,
            "RMC_OPERATOR_SURFACE_STRIP_VISIBLE": False,
            "RMC_OPERATOR_SURFACE_SPINE": [],
            "RMC_OPERATOR_PAIRED_LINKS": [],
            "RMC_OPERATOR_SURFACE_CURRENT": None,
        }

    spine = build_operator_surface_spine(request)
    paired = build_paired_surface_links(request)
    strip_visible = _operator_surface_strip_visible(request) and bool(spine)
    return {
        "RMC_OPERATOR_SURFACE_IA": bool(spine),
        "RMC_OPERATOR_SURFACE_STRIP_VISIBLE": strip_visible,
        "RMC_OPERATOR_SURFACE_SPINE": spine,
        "RMC_OPERATOR_PAIRED_LINKS": paired if strip_visible else [],
        "RMC_OPERATOR_SURFACE_CURRENT": _detect_operator_surface(request),
    }


def build_surface_parity_matrix() -> dict[str, Any]:
    """Machine-readable audit rows for verify_super_admin_surface_parity.py."""
    spine_rows = []
    for surface, url_name, label, _icon in OPERATOR_SURFACE_SPINE_SPECS:
        spine_rows.append(
            {
                "surface": surface,
                "url_name": url_name,
                "label": str(label),
                "url": _safe_reverse(url_name),
                "ok": _safe_reverse(url_name) is not None,
            }
        )

    paired_rows = []
    for spec in SUPER_FIRST_PAIRED_SPECS:
        super_url = (spec.get("super_url_name") or "").strip()
        bridge_key = (spec.get("bridge_key") or "").strip()
        row = {
            "slug": spec["slug"],
            "label": str(spec["label"]),
            "super_url_name": super_url or None,
            "super_url": _safe_reverse(super_url) if super_url else None,
            "bridge_key": bridge_key or None,
            "admin_bridge_url": (
                _safe_reverse("super:admin_bridge", kwargs={"bridge_key": bridge_key})
                if bridge_key
                else None
            ),
            "bridge_registered": bool(
                bridge_key and bridge_key in PLATFORM_ADMIN_BRIDGES
            ),
        }
        row["ok"] = (not super_url or row["super_url"] is not None) and (
            not bridge_key
            or (row["bridge_registered"] and row["admin_bridge_url"] is not None)
        )
        paired_rows.append(row)

    view_binding_rows = []
    for url_name, bridge_key in sorted(SUPER_VIEW_BRIDGE_BINDINGS.items()):
        row = {
            "super_url_name": f"super:{url_name}",
            "super_url": _safe_reverse(f"super:{url_name}"),
            "bridge_key": bridge_key,
            "bridge_registered": bridge_key in PLATFORM_ADMIN_BRIDGES,
            "admin_bridge_url": _safe_reverse(
                "super:admin_bridge", kwargs={"bridge_key": bridge_key}
            ),
        }
        row["ok"] = (
            row["super_url"] is not None
            and row["bridge_registered"]
            and row["admin_bridge_url"] is not None
        )
        view_binding_rows.append(row)

    prefix_rows = []
    for prefix, bridge_key in SUPER_PATH_PREFIX_BRIDGE_BINDINGS:
        prefix_rows.append(
            {
                "path_prefix": prefix,
                "bridge_key": bridge_key,
                "bridge_registered": bridge_key in PLATFORM_ADMIN_BRIDGES,
                "ok": bridge_key in PLATFORM_ADMIN_BRIDGES,
            }
        )

    browser_rows = build_browser_parity_probe_matrix()

    bindings_ok = all(r["ok"] for r in view_binding_rows) and all(
        r["ok"] for r in prefix_rows
    )
    browser_ok = all(r["ok"] for r in browser_rows)

    return {
        "version": "2026.05.16.1",
        "spine": spine_rows,
        "super_first_pairs": paired_rows,
        "super_view_bindings": view_binding_rows,
        "super_path_prefix_bindings": prefix_rows,
        "browser_probes": browser_rows,
        "spine_ok": all(r["ok"] for r in spine_rows),
        "pairs_ok": all(r["ok"] for r in paired_rows),
        "bindings_ok": bindings_ok,
        "browser_probes_ok": browser_ok,
    }


def build_browser_parity_probe_matrix() -> list[dict[str, Any]]:
    """Resolved HTTP paths for Playwright manager surface parity."""
    rows: list[dict[str, Any]] = []
    for probe in MANAGER_BROWSER_PARITY_PROBES:
        path_name = str(probe.get("path_name") or "")
        path = _safe_reverse(path_name) if path_name else None
        row = {
            "slug": probe["slug"],
            "path_name": path_name,
            "path": path,
            "expect_strip": bool(probe.get("expect_strip")),
            "expect_paired": bool(probe.get("expect_paired")),
            "paired_operator": bool(probe.get("paired_operator")),
            "ok": path is not None,
        }
        rows.append(row)
    return rows
