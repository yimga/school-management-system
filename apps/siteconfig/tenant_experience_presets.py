"""Shopify-style portal experience presets (tenant_experience_policy bundles)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.siteconfig.tenant_experience_policy import (
    _deep_merge_policy,
    tenant_experience_policy_defaults,
)

PRESET_MINIMAL_V3 = "minimal_v3"
PRESET_FULL_LEGACY_ON_V3 = "full_legacy_bands_on_v3"
PRESET_PARENT_PORTAL = "parent_portal_focus"
PRESET_LEGACY_SHELL = "legacy_shell"
PRESET_CUSTOM = "custom"

EXPERIENCE_PRESET_IDS: frozenset[str] = frozenset(
    {
        PRESET_CUSTOM,
        PRESET_MINIMAL_V3,
        PRESET_FULL_LEGACY_ON_V3,
        PRESET_PARENT_PORTAL,
        PRESET_LEGACY_SHELL,
    }
)

EXPERIENCE_PRESET_CHOICES: tuple[tuple[str, str], ...] = (
    (PRESET_CUSTOM, _("Custom (manual tweaks)")),
    (PRESET_MINIMAL_V3, _("Minimal v3")),
    (PRESET_FULL_LEGACY_ON_V3, _("Full legacy bands on v3")),
    (PRESET_PARENT_PORTAL, _("Parent portal focus")),
    (PRESET_LEGACY_SHELL, _("Full legacy shell")),
)

ROLE_HOME_MODE_V3 = "v3_canvas"
ROLE_HOME_MODE_LEGACY = "legacy_stack"

ROLE_HOME_EXPERIENCE_MODE_CHOICES: tuple[tuple[str, str], ...] = (
    (ROLE_HOME_MODE_V3, _("v3 role-home canvas (default)")),
    (ROLE_HOME_MODE_LEGACY, _("Legacy stack on role homes only")),
)

ROLE_PRESET_INHERIT = "inherit"

ROLE_PRESET_BUCKETS: dict[str, dict[str, str]] = {
    "ADMIN_OPERATOR": {"label": str(_("Admin / operator"))},
    "TEACHER": {"label": str(_("Teacher"))},
    "PARENT": {"label": str(_("Parent"))},
    "STUDENT": {"label": str(_("Student"))},
}

ROLE_PRESET_FIELD_CHOICES: tuple[tuple[str, str], ...] = (
    (ROLE_PRESET_INHERIT, _("Inherit school default")),
    *EXPERIENCE_PRESET_CHOICES,
)

# Keys compared when detecting whether a stored policy still matches a preset.
_PRESET_COMPARE_KEYS: tuple[str, ...] = (
    "use_v3_shell",
    "show_mission_strip",
    "hide_mission_strip_after_launch",
    "show_experience_command_strip",
    "show_security_posture_inline",
    "show_mfa_nudge",
    "show_legacy_explain_strip",
    "show_next_action_strip",
    "show_community_band_on_v3",
    "show_newsletter_band_on_v3",
    "show_proactive_help_nudge",
    "show_lifecycle_concierge",
    "show_kb_ai_panel",
    "show_legacy_ai_copilot_dock",
    "ai_layer_strip_mode",
    "ai_copilot_rail_mode",
    "role_home_experience_mode",
    "show_first_run_zero_state_on_v3",
    "show_smart_action_hub_on_v3",
    "show_portal_chathead_on_v3",
    "show_header_home_link_on_v3",
    "show_workspace_os_header_on_v3",
    "show_operator_console_strip_on_v3",
    "show_os_status_strip_on_v3",
    "show_zero_click_command_strip_on_v3",
    "show_dashboard_stats_cards_on_v3",
    "show_legacy_sidebar_user_header_on_v3",
)

ROLE_PRESET_MERGE_KEYS: frozenset[str] = frozenset(
    {
        *_PRESET_COMPARE_KEYS,
        "experience_score_label",
        "experience_score_profile_weight",
        "experience_score_school_weight",
        "experience_score_ready_threshold",
        "experience_score_attention_threshold",
        "experience_score_country_bonus",
    }
)

ADMIN_OPERATOR_ROLES: frozenset[str] = frozenset(
    {
        "ADMIN",
        "SUPERADMIN",
        "BURSAR",
        "IT_ADMIN",
        "PRINCIPAL",
        "LEADERSHIP",
        "SECRETARY",
        "PROPRIETOR",
    }
)

_ALL_LEGACY_ON_V3_TRUE: dict[str, bool] = {
    "show_first_run_zero_state_on_v3": True,
    "show_smart_action_hub_on_v3": True,
    "show_portal_chathead_on_v3": True,
    "show_header_home_link_on_v3": True,
    "show_workspace_os_header_on_v3": True,
    "show_operator_console_strip_on_v3": True,
    "show_os_status_strip_on_v3": True,
    "show_zero_click_command_strip_on_v3": True,
    "show_dashboard_stats_cards_on_v3": True,
    "show_legacy_sidebar_user_header_on_v3": True,
    "show_legacy_explain_strip": True,
    "show_next_action_strip": True,
    "show_security_posture_inline": True,
    "show_proactive_help_nudge": True,
}

_PRESET_OVERLAYS: dict[str, dict[str, Any]] = {
    PRESET_MINIMAL_V3: {
        "use_v3_shell": True,
        "role_home_experience_mode": ROLE_HOME_MODE_V3,
        "show_mission_strip": True,
        "show_experience_command_strip": True,
        "hide_mission_strip_after_launch": False,
        "show_security_posture_inline": False,
        "show_mfa_nudge": False,
        "show_legacy_explain_strip": False,
        "show_next_action_strip": False,
        "show_community_band_on_v3": False,
        "show_newsletter_band_on_v3": False,
        "show_proactive_help_nudge": False,
        "show_lifecycle_concierge": False,
        "show_kb_ai_panel": False,
        "show_legacy_ai_copilot_dock": False,
        "ai_layer_strip_mode": "inherit",
        "ai_copilot_rail_mode": "inherit",
        "setup_surface_enabled": True,
        **{key: False for key in _ALL_LEGACY_ON_V3_TRUE if key.startswith("show_")},
    },
    PRESET_FULL_LEGACY_ON_V3: {
        "use_v3_shell": True,
        "role_home_experience_mode": ROLE_HOME_MODE_V3,
        "show_mission_strip": True,
        "show_experience_command_strip": True,
        **_ALL_LEGACY_ON_V3_TRUE,
        "show_community_band_on_v3": True,
        "show_newsletter_band_on_v3": True,
        "show_lifecycle_concierge": True,
        "show_kb_ai_panel": True,
        "show_legacy_ai_copilot_dock": True,
    },
    PRESET_PARENT_PORTAL: {
        "use_v3_shell": True,
        "role_home_experience_mode": ROLE_HOME_MODE_V3,
        "show_mission_strip": True,
        "show_experience_command_strip": True,
        "show_portal_chathead_on_v3": True,
        "show_proactive_help_nudge": True,
        "show_legacy_explain_strip": False,
        "show_workspace_os_header_on_v3": False,
        "show_operator_console_strip_on_v3": False,
        "show_zero_click_command_strip_on_v3": False,
        "show_smart_action_hub_on_v3": False,
        "experience_score_label": "",
        "experience_score_profile_weight": 60,
        "experience_score_school_weight": 40,
        "experience_score_country_bonus": 10,
        "experience_score_ready_threshold": 70,
        "experience_score_attention_threshold": 45,
    },
    PRESET_LEGACY_SHELL: {
        "use_v3_shell": False,
        "role_home_experience_mode": ROLE_HOME_MODE_LEGACY,
        "show_mission_strip": False,
        "show_experience_command_strip": True,
    },
}


def preset_catalog() -> list[dict[str, Any]]:
    """Operator-facing preset cards (i18n labels + short descriptions)."""
    return [
        {
            "id": PRESET_MINIMAL_V3,
            "label": str(_("Minimal v3")),
            "description": str(
                _("Clean v3 canvas — mission strip + command strip only; no legacy bands.")
            ),
            "icon": "bi-diamond",
        },
        {
            "id": PRESET_FULL_LEGACY_ON_V3,
            "label": str(_("Full legacy bands on v3")),
            "description": str(
                _("Keep v3 header/canvas but restore every legacy workspace band.")
            ),
            "icon": "bi-layers",
        },
        {
            "id": PRESET_PARENT_PORTAL,
            "label": str(_("Parent portal focus")),
            "description": str(
                _("Family-first: messages, country rails bonus, lighter operator chrome.")
            ),
            "icon": "bi-people",
        },
        {
            "id": PRESET_LEGACY_SHELL,
            "label": str(_("Full legacy shell")),
            "description": str(
                _("One-click switch to the classic portal stack for the whole tenant.")
            ),
            "icon": "bi-arrow-counterclockwise",
        },
    ]


def apply_experience_preset(preset_id: str, *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a full policy dict for ``preset_id`` merged onto defaults."""
    preset = str(preset_id or PRESET_CUSTOM).strip().lower()
    if preset not in EXPERIENCE_PRESET_IDS or preset == PRESET_CUSTOM:
        merged = _deep_merge_policy(tenant_experience_policy_defaults(), base or {})
        merged["experience_preset"] = PRESET_CUSTOM
        return merged
    overlay = _PRESET_OVERLAYS.get(preset, {})
    merged = _deep_merge_policy(tenant_experience_policy_defaults(), overlay)
    if base:
        merged = _deep_merge_policy(merged, base)
    merged["experience_preset"] = preset
    return merged


def policy_matches_preset(policy: dict[str, Any], preset_id: str) -> bool:
    if preset_id not in _PRESET_OVERLAYS:
        return False
    expected = apply_experience_preset(preset_id)
    for key in _PRESET_COMPARE_KEYS:
        if expected.get(key) != policy.get(key):
            return False
    return True


def detect_matching_preset(policy: dict[str, Any]) -> str:
    for preset_id in (
        PRESET_MINIMAL_V3,
        PRESET_FULL_LEGACY_ON_V3,
        PRESET_PARENT_PORTAL,
        PRESET_LEGACY_SHELL,
    ):
        if policy_matches_preset(policy, preset_id):
            return preset_id
    return PRESET_CUSTOM


def merge_manual_fields_onto_policy(
    policy: dict[str, Any], cleaned: dict[str, Any]
) -> dict[str, Any]:
    """Overlay operator-edited flat ``txp_*`` fields onto a preset base."""
    from apps.siteconfig.forms_cockpit import build_tenant_experience_policy_from_cleaned

    manual = build_tenant_experience_policy_from_cleaned(cleaned)
    out = _deep_merge_policy(policy, manual)
    preset = str(cleaned.get("txp_experience_preset") or "").strip().lower()
    if preset in EXPERIENCE_PRESET_IDS and preset != PRESET_CUSTOM:
        out["experience_preset"] = preset
    else:
        out["experience_preset"] = detect_matching_preset(out)
    return out


def normalize_role_experience_presets(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        bucket = str(key or "").strip().upper()
        preset = str(value or "").strip().lower()
        if bucket in ROLE_PRESET_BUCKETS and preset:
            out[bucket] = preset
    return out


def experience_policy_role_bucket(role: str) -> str:
    role_upper = str(role or "").strip().upper()
    if role_upper in ADMIN_OPERATOR_ROLES:
        return "ADMIN_OPERATOR"
    if role_upper == "TEACHER":
        return "TEACHER"
    if role_upper == "PARENT":
        return "PARENT"
    if role_upper == "STUDENT":
        return "STUDENT"
    return "ADMIN_OPERATOR"


def merge_role_preset_onto_policy(policy: dict[str, Any], role: str) -> dict[str, Any]:
    bucket = experience_policy_role_bucket(role)
    role_presets = normalize_role_experience_presets(policy.get("role_experience_presets"))
    preset_id = role_presets.get(bucket, ROLE_PRESET_INHERIT)
    out = dict(policy)
    out["effective_experience_preset"] = str(policy.get("experience_preset") or PRESET_CUSTOM)
    if preset_id in {"", ROLE_PRESET_INHERIT}:
        return out
    overlay = apply_experience_preset(preset_id)
    merged = _deep_merge_policy(out, {k: overlay[k] for k in ROLE_PRESET_MERGE_KEYS if k in overlay})
    if preset_id == PRESET_LEGACY_SHELL:
        merged["role_home_experience_mode"] = ROLE_HOME_MODE_LEGACY
    merged["effective_experience_preset"] = preset_id
    return merged


def apply_role_overlay(
    policy: dict[str, Any], *, role_bucket: str, preset_id: str
) -> dict[str, Any]:
    out = dict(policy)
    presets = normalize_role_experience_presets(out.get("role_experience_presets"))
    bucket = str(role_bucket or "").strip().upper()
    preset = str(preset_id or ROLE_PRESET_INHERIT).strip().lower()
    if preset in {"", "inherit", "school", "tenant"}:
        presets.pop(bucket, None)
    elif bucket in ROLE_PRESET_BUCKETS:
        presets[bucket] = preset
    out["role_experience_presets"] = presets
    return out


__all__ = [
    "ADMIN_OPERATOR_ROLES",
    "EXPERIENCE_PRESET_CHOICES",
    "EXPERIENCE_PRESET_IDS",
    "PRESET_CUSTOM",
    "PRESET_FULL_LEGACY_ON_V3",
    "PRESET_LEGACY_SHELL",
    "PRESET_MINIMAL_V3",
    "PRESET_PARENT_PORTAL",
    "ROLE_HOME_EXPERIENCE_MODE_CHOICES",
    "ROLE_HOME_MODE_LEGACY",
    "ROLE_HOME_MODE_V3",
    "ROLE_PRESET_BUCKETS",
    "ROLE_PRESET_INHERIT",
    "ROLE_PRESET_MERGE_KEYS",
    "apply_experience_preset",
    "apply_role_overlay",
    "detect_matching_preset",
    "experience_policy_role_bucket",
    "merge_manual_fields_onto_policy",
    "merge_role_preset_onto_policy",
    "normalize_role_experience_presets",
    "policy_matches_preset",
    "preset_catalog",
]
