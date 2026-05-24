"""
Premium portal / operator dashboard visual preset catalog (v3.62.20).

Tenants and operators pick a preset slug via DashboardUserPreference.role_visual_presets
or SiteSettings cockpit overrides. Each preset maps to dashboard layout density,
chrome family, and landing partial set — aligned to
``docs/generated/preview_app_shell_tenant_portal_v3_100x.html`` and manager v8 200x.

Minimum catalog size: 50 unique presets (25 tenant-facing + 25 operator-facing).
"""
from __future__ import annotations

from typing import Any, Final, TypedDict


class PortalVisualPreset(TypedDict):
    slug: str
    label: str
    surface: str  # "tenant" | "operator"
    roles: tuple[str, ...]
    density: str  # compact | balanced | editorial
    layout_family: str
    preview_ref: str


_TENANT_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("parent", "Parent", "family-hub"),
    ("teacher", "Teacher", "classroom-command"),
    ("student", "Student", "learning-home"),
    ("admin", "School admin", "operations-console"),
    ("staff", "Staff", "front-office"),
)

_TENANT_VARIANTS: tuple[tuple[str, str], ...] = (
    ("soft-glass", "Soft glass"),
    ("crisp-pro", "Crisp professional"),
    ("warm-campus", "Warm campus"),
    ("midnight-focus", "Midnight focus"),
    ("daylight-clear", "Daylight clear"),
)

_OPERATOR_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("founder", "Founder", "executive-cockpit"),
    ("super", "Platform super", "control-plane-200x"),
    ("migration", "Migration cloud", "trust-migration"),
    ("finance", "Finance ops", "revenue-ops"),
    ("studio", "Studio OS", "brand-studio"),
)

_OPERATOR_VARIANTS: tuple[tuple[str, str], ...] = (
    ("v8-200x", "v8 200x luxury"),
    ("v8-compact", "v8 compact"),
    ("v8-editorial", "v8 editorial"),
    ("v8-trust", "v8 trust-forward"),
    ("v8-velocity", "v8 velocity"),
)


def _build_tenant_presets() -> list[PortalVisualPreset]:
    out: list[PortalVisualPreset] = []
    for fam_slug, fam_label, layout in _TENANT_FAMILIES:
        for var_slug, var_label in _TENANT_VARIANTS:
            slug = f"tenant-{fam_slug}-{var_slug}"
            out.append(
                PortalVisualPreset(
                    slug=slug,
                    label=f"{fam_label} · {var_label}",
                    surface="tenant",
                    roles=(
                        "PARENT"
                        if fam_slug == "parent"
                        else "TEACHER"
                        if fam_slug == "teacher"
                        else "STUDENT"
                        if fam_slug == "student"
                        else "ADMIN"
                        if fam_slug == "admin"
                        else "STAFF"
                    ),
                    density="compact" if "compact" in var_slug or "midnight" in var_slug else "balanced",
                    layout_family=layout,
                    preview_ref="preview_app_shell_tenant_portal_v3_100x.html",
                )
            )
    return out


def _build_operator_presets() -> list[PortalVisualPreset]:
    out: list[PortalVisualPreset] = []
    for fam_slug, fam_label, layout in _OPERATOR_FAMILIES:
        for var_slug, var_label in _OPERATOR_VARIANTS:
            slug = f"operator-{fam_slug}-{var_slug}"
            out.append(
                PortalVisualPreset(
                    slug=slug,
                    label=f"{fam_label} · {var_label}",
                    surface="operator",
                    roles=("OPERATOR", "ADMIN", "IT_ADMIN", "LEADERSHIP"),
                    density="compact" if "compact" in var_slug or "velocity" in var_slug else "editorial",
                    layout_family=layout,
                    preview_ref="preview_app_shell_manager_v8_200x.html",
                )
            )
    return out


PORTAL_VISUAL_PRESETS: Final[tuple[PortalVisualPreset, ...]] = tuple(
    _build_tenant_presets() + _build_operator_presets()
)

if len(PORTAL_VISUAL_PRESETS) != 50:
    raise RuntimeError(f"expected 50 presets, got {len(PORTAL_VISUAL_PRESETS)}")


def preset_slugs() -> frozenset[str]:
    return frozenset(p["slug"] for p in PORTAL_VISUAL_PRESETS)


def choices_for_role(role: str | None = None) -> list[tuple[str, str]]:
    role_code = (role or "").upper()
    rows: list[tuple[str, str]] = []
    for preset in PORTAL_VISUAL_PRESETS:
        if role_code and role_code not in preset["roles"] and role_code != "OPERATOR":
            if preset["surface"] == "operator" and role_code not in (
                "ADMIN",
                "IT_ADMIN",
                "LEADERSHIP",
                "PROPRIETOR",
            ):
                continue
            if preset["surface"] == "tenant" and role_code not in preset["roles"]:
                continue
        rows.append((preset["slug"], preset["label"]))
    return rows


def resolve_preset(slug: str | None, *, role: str | None = None) -> PortalVisualPreset | None:
    if not slug:
        return None
    for preset in PORTAL_VISUAL_PRESETS:
        if preset["slug"] == slug:
            return preset
    return None


def default_slug_for_role(role: str | None, *, surface: str = "tenant") -> str:
    role_code = (role or "").upper()
    if surface == "operator" or role_code in ("OPERATOR", "IT_ADMIN", "LEADERSHIP", "PROPRIETOR"):
        return "operator-super-v8-200x"
    if role_code == "TEACHER":
        return "tenant-teacher-crisp-pro"
    if role_code == "PARENT":
        return "tenant-parent-soft-glass"
    if role_code == "STUDENT":
        return "tenant-student-daylight-clear"
    if role_code == "ADMIN":
        return "tenant-admin-crisp-pro"
    return "tenant-staff-warm-campus"


def as_cockpit_payload() -> dict[str, Any]:
    """Serialize for SiteSettings.cockpit_payload portal_template_catalog."""
    return {
        "version": 1,
        "count": len(PORTAL_VISUAL_PRESETS),
        "presets": [
            {
                "slug": p["slug"],
                "label": p["label"],
                "surface": p["surface"],
                "roles": list(p["roles"]),
                "density": p["density"],
                "layout_family": p["layout_family"],
                "preview_ref": p["preview_ref"],
            }
            for p in PORTAL_VISUAL_PRESETS
        ],
    }
