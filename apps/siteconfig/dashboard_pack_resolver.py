"""
Dashboard-pack resolution — the single junction that connects the dashboard-pack
*catalog* (DashboardPack / DashboardTemplate) to the *cockpit* (DashboardPackAssignment
/ TenantLayoutAssignment), to per-user choice (DashboardUserPreference.role_dashboard_packs),
and to the live role-home render overlay.

See docs/DASHBOARD_PACKS_REVIVAL_PLAN.md. This module is deliberately the one place
the precedence chain lives so it can be unit-tested in isolation:

    render precedence (highest first):
      per-user pack choice  →  TenantLayoutAssignment(school, role)
        →  DashboardPackAssignment(school, role)  →  hardcoded ROLE_HOME_CONFIG default

No hardcoded pack *slug* is selected at runtime: the default pack for a role is chosen
through the config cascade (school.primary_sector → pack family → first active pack),
per CLAUDE.md no-hardcoding. The role-home default always wins when nothing is assigned,
so a brand-new school never renders blank.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Resolution must never break a dashboard render. Reads are best-effort.
_RESOLVER_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    LookupError,
)


# ---------------------------------------------------------------------------
# Role bucketing: fine-grained user roles map down to one of the coarse
# TenantLayoutAssignment.ROLE_CHOICES buckets used for pack assignment.
# ---------------------------------------------------------------------------
# PRIMARY pack family per coarse assignment role — drives the *default* assignment at
# provisioning. The sector cascade discriminates within this family.
_DEFAULT_PACK_FAMILY_BY_ROLE: dict[str, str] = {
    "STUDENT": "student",  # role-string-allow: dashboard-pack-family-default-map
    "TEACHER": "teacher",  # role-string-allow: dashboard-pack-family-default-map
    "PARENT": "parent",  # role-string-allow: dashboard-pack-family-default-map
    "ADMIN": "admin",  # role-string-allow: dashboard-pack-family-default-map
    "LEADERSHIP": "principal",
    "IT_ADMIN": "it_admin",
}

# All pack families a user in a coarse role may SWITCH between. The coarse 6-role bucket
# (TenantLayoutAssignment.ROLE_CHOICES) is intentionally broad — the catch-all ADMIN
# bucket carries many fine staff roles (bursar, registrar, secretary, nurse, …), so it
# can switch among every role-specialized ops dashboard. Every seeded family appears in
# exactly one list so no seeded pack is left orphaned/unreachable.
_SWITCHABLE_FAMILIES_BY_ROLE: dict[str, list[str]] = {
    "STUDENT": ["student"],  # role-string-allow: dashboard-pack-switch-families
    "TEACHER": ["teacher"],  # role-string-allow: dashboard-pack-switch-families
    "PARENT": ["parent"],  # role-string-allow: dashboard-pack-switch-families
    "LEADERSHIP": ["principal"],
    "IT_ADMIN": ["it_admin", "compliance"],
    "ADMIN": [  # role-string-allow: dashboard-pack-switch-families
        "admin",
        "finance",
        "admissions",
        "registrar",
        "counselor",
        "hr",
        "nurse",
        "transport",
        "library",
        "boarding",
        "cafeteria",
        "alumni",
        "compact",
    ],
}

# Fine user role → coarse assignment-role bucket. Anything unmapped falls back to ADMIN.
_ASSIGNMENT_ROLE_BY_USER_ROLE: dict[str, str] = {
    "STUDENT": "STUDENT",  # role-string-allow: dashboard-pack-role-bucket
    "PARENT": "PARENT",  # role-string-allow: dashboard-pack-role-bucket
    "TEACHER": "TEACHER",  # role-string-allow: dashboard-pack-role-bucket
    "IT_ADMIN": "IT_ADMIN",
    "PRINCIPAL": "LEADERSHIP",
    "VICE_PRINCIPAL": "LEADERSHIP",
    "LEADERSHIP": "LEADERSHIP",
    "PROPRIETOR": "LEADERSHIP",  # role-string-allow: dashboard-pack-role-bucket
    "ADMIN": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "SECRETARY": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "ACADEMICS_STAFF": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "REGISTRAR": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "BURSAR": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "ACCOUNTANT": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "FINANCE_STAFF": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "COMMS_STAFF": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "EXECUTIVE_ASSISTANT": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
    "VIRTUAL_ASSISTANT": "ADMIN",  # role-string-allow: dashboard-pack-role-bucket
}

_FALLBACK_ASSIGNMENT_ROLE = "ADMIN"  # role-string-allow: dashboard-pack-role-bucket-fallback


def assignment_roles() -> list[str]:
    """The coarse roles we seed/assign packs for (== TenantLayoutAssignment.ROLE_CHOICES)."""
    from apps.siteconfig.models_dashboard import TenantLayoutAssignment

    return [choice[0] for choice in TenantLayoutAssignment.ROLE_CHOICES]


def assignment_role_for_user_role(user_role: str | None) -> str:
    """Map a fine-grained user role to its coarse pack-assignment bucket."""
    code = (user_role or "").strip().upper()
    return _ASSIGNMENT_ROLE_BY_USER_ROLE.get(code, _FALLBACK_ASSIGNMENT_ROLE)


def _school_sector(school: Any) -> str:
    return (getattr(school, "primary_sector", "") or "").strip().upper()


def available_packs_for_role(assignment_role: str) -> list[dict[str, str]]:
    """
    Active packs a user in this coarse role may switch between (all the role's switchable
    families). Returns a list of {"code", "name", "description"} dicts, name-ordered.
    """
    from apps.siteconfig.models_dashboard import DashboardPack

    role = (assignment_role or "").strip().upper()
    families = _SWITCHABLE_FAMILIES_BY_ROLE.get(role)
    if not families:
        # Fall back to the primary family if the role has no explicit switch list.
        primary = _DEFAULT_PACK_FAMILY_BY_ROLE.get(role)
        families = [primary] if primary else []
    if not families:
        return []
    try:
        rows = DashboardPack.objects.filter(
            is_active=True, family__in=families
        ).order_by("family", "name")
        return [
            {"code": p.code, "name": p.name, "description": p.description or ""}
            for p in rows
        ]
    except _RESOLVER_ERRORS:
        return []


def available_pack_codes_for_role(assignment_role: str) -> set[str]:
    """Set of pack codes the role may legitimately choose (read-time gate)."""
    return {p["code"] for p in available_packs_for_role(assignment_role)}


def available_packs_for_user(user: Any) -> list[dict[str, str]]:
    """Packs the given user may switch between, by their coarse-role bucket."""
    return available_packs_for_role(assignment_role_for_user_role(getattr(user, "role", "")))


# ---------------------------------------------------------------------------
# Default selection via the config cascade (sector → family → first active).
# ---------------------------------------------------------------------------
def default_pack_for_role(school: Any, assignment_role: str) -> Any | None:
    """
    Resolve the default DashboardPack for (school, coarse role) through the cascade:
      1. a pack in the role's family whose recommended_sectors includes the school sector,
      2. else the first active pack in the role's family,
      3. else None (caller keeps the hardcoded role-home default — never blank).
    """
    from apps.siteconfig.models_dashboard import DashboardPack

    family = _DEFAULT_PACK_FAMILY_BY_ROLE.get(
        (assignment_role or "").strip().upper()
    )
    if not family:
        return None
    try:
        family_qs = list(
            DashboardPack.objects.filter(is_active=True, family=family).order_by(
                "name"
            )
        )
    except _RESOLVER_ERRORS:
        return None
    if not family_qs:
        return None

    sector = _school_sector(school)
    if sector:
        for pack in family_qs:
            sectors = pack.recommended_sectors or []
            if isinstance(sectors, list) and sector in {
                str(s).strip().upper() for s in sectors
            }:
                return pack
    return family_qs[0]


def default_template_for_pack(pack: Any) -> Any | None:
    """First active DashboardTemplate belonging to the pack, if any."""
    if pack is None:
        return None
    from apps.siteconfig.models_dashboard import DashboardTemplate

    try:
        return (
            DashboardTemplate.objects.filter(dashboard_pack=pack, is_active=True)
            .order_by("name")
            .first()
        )
    except _RESOLVER_ERRORS:
        return None


# ---------------------------------------------------------------------------
# Provisioning + backfill: idempotent assignment of default packs per role.
# ---------------------------------------------------------------------------
def assign_default_dashboard_packs(school: Any, *, apply: bool = True) -> dict[str, Any]:
    """
    Ensure each coarse role for ``school`` has a DashboardPackAssignment +
    TenantLayoutAssignment pointing at its default pack/template.

    Idempotent: keyed on the (school, role) unique_together; never overwrites an
    operator's existing choice. Returns a summary dict. ``apply=False`` is a dry run.
    """
    from apps.siteconfig.models_dashboard import (
        DashboardPackAssignment,
        TenantLayoutAssignment,
    )

    summary: dict[str, Any] = {
        "school": str(getattr(school, "pk", "") or ""),
        "applied": bool(apply),
        "pack_assignments_created": 0,
        "layout_assignments_created": 0,
        "roles": [],
        "skipped_no_pack": [],
    }
    if school is None:
        return summary

    for role in assignment_roles():
        pack = default_pack_for_role(school, role)
        if pack is None:
            summary["skipped_no_pack"].append(role)
            continue
        template = default_template_for_pack(pack)
        row = {"role": role, "pack": pack.code, "template": getattr(template, "name", None)}
        summary["roles"].append(row)
        if not apply:
            continue

        _, pack_created = DashboardPackAssignment.objects.get_or_create(
            school=school,
            role=role,
            defaults={"dashboard_pack": pack, "is_active": True},
        )
        if pack_created:
            summary["pack_assignments_created"] += 1

        if template is not None:
            _, layout_created = TenantLayoutAssignment.objects.get_or_create(
                school=school,
                role=role,
                defaults={"template": template, "is_active": True},
            )
            if layout_created:
                summary["layout_assignments_created"] += 1

    return summary


# ---------------------------------------------------------------------------
# Render-time overlay: resolve the effective template for a request, then overlay
# its config_schema["role_home"] + styling_overrides onto the role-home structure.
# ---------------------------------------------------------------------------
def _template_for_pack_code(pack_code: str) -> Any | None:
    if not pack_code:
        return None
    from apps.siteconfig.models_dashboard import DashboardPack

    try:
        pack = DashboardPack.objects.filter(code=pack_code, is_active=True).first()
    except _RESOLVER_ERRORS:
        return None
    return default_template_for_pack(pack)


def _user_chosen_pack_code(user: Any, assignment_role: str) -> str:
    """Per-user dashboard-pack choice (Phase 3), if the field/method is present."""
    try:
        prefs = getattr(user, "dashboard_preferences", None)
        getter = getattr(prefs, "get_dashboard_pack", None)
        if callable(getter):
            return (getter(assignment_role) or "").strip()
    except _RESOLVER_ERRORS:
        return ""
    return ""


def resolve_effective_template(request: Any) -> dict[str, Any]:
    """
    Resolve the effective DashboardTemplate + provenance for the request, honoring
    the precedence chain. Returns a dict:
        {"template": <DashboardTemplate|None>, "styling_overrides": {...},
         "source": "user"|"tenant_layout"|"pack_assignment"|"default",
         "assignment_role": <coarse role>, "pack_code": <str|"">}
    Safe on a brand-new school (returns source="default", template=None).
    """
    out: dict[str, Any] = {
        "template": None,
        "styling_overrides": {},
        "source": "default",
        "assignment_role": "",
        "pack_code": "",
    }
    school = getattr(request, "school", None)
    user = getattr(request, "user", None)
    if not school or not user or not getattr(user, "is_authenticated", False):
        return out

    assignment_role = assignment_role_for_user_role(getattr(user, "role", ""))
    out["assignment_role"] = assignment_role

    # 1) Per-user pack choice. Re-gated to the role's allowed set at READ time too, so a
    #    stale choice (role changed, or pack re-familied) silently falls through to the
    #    school/role default instead of rendering a foreign-family dashboard.
    chosen = _user_chosen_pack_code(user, assignment_role)
    if chosen and chosen in available_pack_codes_for_role(assignment_role):
        template = _template_for_pack_code(chosen)
        if template is not None:
            out.update({"template": template, "source": "user", "pack_code": chosen})
            return out

    # 2) TenantLayoutAssignment(school, coarse role) → template (+ styling overrides).
    try:
        from apps.siteconfig.models_dashboard import TenantLayoutAssignment

        layout = (
            TenantLayoutAssignment.objects.filter(
                school_id=school.pk, role=assignment_role, is_active=True
            )
            .select_related("template", "template__dashboard_pack")
            .first()
        )
        if layout and layout.template and layout.template.is_active:
            pack = getattr(layout.template, "dashboard_pack", None)
            out.update(
                {
                    "template": layout.template,
                    "styling_overrides": layout.styling_overrides or {},
                    "source": "tenant_layout",
                    "pack_code": getattr(pack, "code", "") or "",
                }
            )
            return out
    except _RESOLVER_ERRORS:
        pass

    # 3) DashboardPackAssignment(school, coarse role) → pack → its default template.
    try:
        from apps.siteconfig.models_dashboard import DashboardPackAssignment

        pa = (
            DashboardPackAssignment.objects.filter(
                school_id=school.pk, role=assignment_role, is_active=True
            )
            .select_related("dashboard_pack")
            .first()
        )
        if pa and pa.dashboard_pack and pa.dashboard_pack.is_active:
            template = default_template_for_pack(pa.dashboard_pack)
            out.update(
                {
                    "template": template,
                    "source": "pack_assignment",
                    "pack_code": pa.dashboard_pack.code,
                }
            )
            return out
    except _RESOLVER_ERRORS:
        pass

    return out


def resolve_effective_template_cached(request: Any) -> dict[str, Any]:
    """resolve_effective_template memoized on the request (one resolution per request).

    Multiple surfaces (portal chrome, role-home overlay, switcher context) resolve the
    same effective template per request; cache it to avoid duplicate queries.
    """
    cached = getattr(request, "_rmc_effective_template", None)
    if isinstance(cached, dict):
        return cached
    result = resolve_effective_template(request)
    try:
        request._rmc_effective_template = result
    except (AttributeError, TypeError):
        pass
    return result


def overlay_role_home(role_home: dict[str, Any], request: Any) -> dict[str, Any]:
    """
    Overlay the effective template's ``config_schema["role_home"]`` + ``styling_overrides``
    onto a resolved role-home dict (from role_home_engine.resolve_role_home).

    Returns a NEW dict (never mutates the caller's). The overlay only *adds/refines*
    presentation keys; the role default's destinations/actions remain intact so the
    blast radius is small and the dashboard is never left blank.
    """
    if not isinstance(role_home, dict):
        return role_home
    result = dict(role_home)
    result.setdefault("dashboard_pack", {"source": "default", "pack_code": "", "template": ""})

    try:
        resolved = resolve_effective_template_cached(request)
    except _RESOLVER_ERRORS:
        return result

    template = resolved.get("template")
    pack_code = resolved.get("pack_code") or ""
    source = resolved.get("source") or "default"

    # Provenance is always recorded (even for source="default") for templates/tests/UI.
    result["dashboard_pack"] = {
        "source": source,
        "pack_code": pack_code,
        "template": getattr(template, "name", "") or "",
        "assignment_role": resolved.get("assignment_role", ""),
    }

    if template is None:
        return result

    schema = getattr(template, "config_schema", None) or {}
    if not isinstance(schema, dict):
        return result

    overlay = schema.get("role_home")
    if isinstance(overlay, dict):
        # Only string/list presentation keys are overlaid; structural keys are ignored.
        for key in (
            "eyebrow",
            "title",
            "purpose",
            "search_hint",
            "queue_label",
            "next_label",
            "recent_label",
        ):
            val = overlay.get(key)
            if isinstance(val, str) and val.strip():
                result[key] = val
        focus = overlay.get("focus_areas")
        if isinstance(focus, list) and focus:
            result["focus_areas"] = [str(f) for f in focus if str(f).strip()]

    # DEPTH: module visibility + KPI priority drive WHAT the dashboard renders.
    modules = schema.get("modules")
    if isinstance(modules, dict) and modules:
        result["dashboard_modules"] = {str(k): bool(v) for k, v in modules.items()}
    kpis = schema.get("kpis")
    if isinstance(kpis, list) and kpis:
        result["dashboard_kpis"] = [str(k) for k in kpis if str(k).strip()]

    # styling_overrides (per-school) takes precedence over the template's theme block.
    styling = resolved.get("styling_overrides") or {}
    theme = schema.get("theme") if isinstance(schema.get("theme"), dict) else {}
    merged_theme = {**theme, **(styling if isinstance(styling, dict) else {})}
    if merged_theme:
        result["dashboard_theme"] = merged_theme

    return result
