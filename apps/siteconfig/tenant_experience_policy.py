"""Tenant-wide portal experience policy (cockpit_payload.tenant_experience_policy)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

_SIDEBAR_DEFAULT_WIDTH = 280
_SIDEBAR_MIN_WIDTH = 200
_SIDEBAR_MAX_WIDTH = 420
_SIDEBAR_RAIL_WIDTH = 44


def tenant_experience_policy_defaults() -> dict[str, Any]:
    """Factory — fresh dict on every call (mutation-safe)."""
    return {
        "use_v3_shell": True,
        "show_mission_strip": True,
        "hide_mission_strip_after_launch": False,
        "show_experience_command_strip": True,
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
        "sidebar_default_width": _SIDEBAR_DEFAULT_WIDTH,
        "sidebar_min_width": _SIDEBAR_MIN_WIDTH,
        "sidebar_max_width": _SIDEBAR_MAX_WIDTH,
        "sidebar_rail_width": _SIDEBAR_RAIL_WIDTH,
        "mission_eyebrow": "",
        "mission_cta_label": "",
        "experience_score_label": "",
        "setup_surface_enabled": True,
        "hidden_setup_wizard_keys": [],
        "show_first_run_zero_state_on_v3": False,
        "show_smart_action_hub_on_v3": False,
        "show_portal_chathead_on_v3": False,
        "show_header_home_link_on_v3": False,
        "show_workspace_os_header_on_v3": False,
        "show_operator_console_strip_on_v3": False,
        "show_os_status_strip_on_v3": False,
        "show_zero_click_command_strip_on_v3": False,
        "show_dashboard_stats_cards_on_v3": False,
        "show_legacy_sidebar_user_header_on_v3": False,
        "experience_preset": "custom",
        "role_home_experience_mode": "v3_canvas",
        "role_experience_presets": {},
        "experience_score_profile_weight": 50,
        "experience_score_school_weight": 50,
        "experience_score_ready_threshold": 75,
        "experience_score_attention_threshold": 50,
        "experience_score_country_bonus": 0,
    }


def _deep_merge_policy(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_policy(out[key], value)
        else:
            out[key] = value
    return out


def _payload_slice(request: HttpRequest | None) -> dict[str, Any]:
    if request is None:
        return {}
    try:
        from apps.siteconfig.cockpit_context import _resolve_cockpit_payload

        payload = _resolve_cockpit_payload(request) or {}
    except Exception:
        return {}
    raw = payload.get("tenant_experience_policy")
    return raw if isinstance(raw, dict) else {}


def _normalize_role_presets(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        bucket = str(key or "").strip().upper()
        preset = str(value or "").strip().lower()
        if bucket and preset:
            out[bucket] = preset
    return out


def resolve_tenant_experience_policy(
    request: HttpRequest | None = None,
    *,
    role: str | None = None,
    apply_role_overlay: bool = True,
) -> dict[str, Any]:
    """Effective tenant experience policy for the current request."""
    from apps.siteconfig.tenant_experience_presets import (
        merge_role_preset_onto_policy,
        normalize_role_experience_presets,
    )

    merged = _deep_merge_policy(
        tenant_experience_policy_defaults(),
        _payload_slice(request),
    )
    merged["sidebar_default_width"] = _clamp_sidebar_width(
        merged.get("sidebar_default_width"), _SIDEBAR_DEFAULT_WIDTH
    )
    merged["sidebar_min_width"] = _clamp_sidebar_width(
        merged.get("sidebar_min_width"), _SIDEBAR_MIN_WIDTH
    )
    merged["sidebar_max_width"] = _clamp_sidebar_width(
        merged.get("sidebar_max_width"), _SIDEBAR_MAX_WIDTH
    )
    merged["sidebar_rail_width"] = _clamp_sidebar_rail_width(
        merged.get("sidebar_rail_width"), _SIDEBAR_RAIL_WIDTH
    )
    hidden = merged.get("hidden_setup_wizard_keys")
    if isinstance(hidden, str):
        merged["hidden_setup_wizard_keys"] = [
            part.strip() for part in hidden.split(",") if part.strip()
        ]
    elif not isinstance(hidden, list):
        merged["hidden_setup_wizard_keys"] = []
    for mode_key in ("ai_layer_strip_mode", "ai_copilot_rail_mode"):
        mode = str(merged.get(mode_key) or "inherit").strip().lower()
        if mode not in {"inherit", "force_on", "force_off"}:
            merged[mode_key] = "inherit"
    preset = str(merged.get("experience_preset") or "custom").strip().lower()
    if preset not in {
        "custom",
        "minimal_v3",
        "full_legacy_bands_on_v3",
        "parent_portal_focus",
        "legacy_shell",
    }:
        merged["experience_preset"] = "custom"
    else:
        merged["experience_preset"] = preset
    role_mode = str(merged.get("role_home_experience_mode") or "v3_canvas").strip().lower()
    if role_mode not in {"v3_canvas", "legacy_stack"}:
        merged["role_home_experience_mode"] = "v3_canvas"
    else:
        merged["role_home_experience_mode"] = role_mode
    merged["role_experience_presets"] = normalize_role_experience_presets(
        merged.get("role_experience_presets")
    )
    merged["experience_score_profile_weight"] = _clamp_score_weight(
        merged.get("experience_score_profile_weight"), 50
    )
    merged["experience_score_school_weight"] = _clamp_score_weight(
        merged.get("experience_score_school_weight"), 50
    )
    merged["experience_score_ready_threshold"] = _clamp_threshold(
        merged.get("experience_score_ready_threshold"), 75
    )
    merged["experience_score_attention_threshold"] = _clamp_threshold(
        merged.get("experience_score_attention_threshold"), 50
    )
    merged["experience_score_country_bonus"] = _clamp_threshold(
        merged.get("experience_score_country_bonus"), 0, maximum=25
    )
    if merged["experience_score_attention_threshold"] > merged["experience_score_ready_threshold"]:
        merged["experience_score_attention_threshold"] = max(
            0, merged["experience_score_ready_threshold"] - 1
        )
    if apply_role_overlay and role:
        merged = merge_role_preset_onto_policy(merged, role)
    return merged


def _clamp_sidebar_width(value: Any, fallback: int) -> int:
    try:
        width = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(_SIDEBAR_MIN_WIDTH, min(_SIDEBAR_MAX_WIDTH, width))


def _clamp_sidebar_rail_width(value: Any, fallback: int) -> int:
    try:
        width = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(36, min(72, width))


def _clamp_score_weight(value: Any, fallback: int) -> int:
    try:
        weight = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(100, weight))


def _clamp_threshold(value: Any, fallback: int, *, maximum: int = 100) -> int:
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(maximum, threshold))


def compute_weighted_experience_score(
    profile_score: int,
    school_score: int,
    policy: dict[str, Any],
    *,
    country_configured: bool = False,
    country_bonus: int | None = None,
) -> int:
    """Weighted composite readiness score (Salesforce-style metadata)."""
    profile_weight = int(policy.get("experience_score_profile_weight", 50))
    school_weight = int(policy.get("experience_score_school_weight", 50))
    total = profile_weight + school_weight
    if total <= 0:
        profile_weight, school_weight, total = 50, 50, 100
    school_value = max(0, min(100, int(school_score)))
    if country_configured:
        bonus = country_bonus
        if bonus is None:
            bonus = int(policy.get("experience_score_country_bonus", 0))
        if bonus > 0:
            school_value = min(100, school_value + bonus)
    profile_value = max(0, min(100, int(profile_score)))
    weighted = (profile_value * profile_weight + school_value * school_weight) / total
    return int(round(weighted))


def experience_score_band(score: int, policy: dict[str, Any]) -> str:
    """Return ``ready`` | ``progress`` | ``attention`` for UI tone."""
    ready = int(policy.get("experience_score_ready_threshold", 75))
    attention = int(policy.get("experience_score_attention_threshold", 50))
    if score >= ready:
        return "ready"
    if score < attention:
        return "attention"
    return "progress"


def role_home_legacy_mode_active(request: HttpRequest) -> bool:
    """Persisted tenant role-home mode (plus optional ``?simple=`` override)."""
    raw = request.GET.get("simple", "")
    token = str(raw).strip().lower()
    if token in {"1", "true", "yes", "legacy"}:
        return True
    if token in {"0", "false", "no", "v3"}:
        return False
    policy = resolve_tenant_experience_policy(request)
    if not bool(policy.get("use_v3_shell", True)):
        return True
    mode = str(policy.get("role_home_experience_mode") or "v3_canvas").lower()
    return mode == "legacy_stack"


def school_has_launched(request: HttpRequest) -> bool:
    school = getattr(request, "school", None)
    if school is None:
        return False
    try:
        from apps.setup_studio.models import SetupProgress

        progress = SetupProgress.objects.filter(school=school).only("launched_at").first()
        return bool(progress and progress.launched_at)
    except Exception:
        return False


def use_v3_shell_for_request(request: HttpRequest) -> bool:
    if getattr(request, "public_host_kind", None) == "manager":
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    policy = resolve_tenant_experience_policy(request)
    return bool(policy.get("use_v3_shell", True))


def _chrome_legacy_or_v3_opt(policy: dict[str, Any], key: str, *, v3: bool, legacy: bool) -> bool:
    if legacy:
        return True
    if not v3:
        return False
    return bool(policy.get(key))


def derive_chrome_flags(
    request: HttpRequest,
    *,
    tp_v3_tenant_shell: bool,
) -> dict[str, bool]:
    """Template-facing booleans for portal chrome gating."""
    policy = resolve_tenant_experience_policy(request)
    v3 = bool(tp_v3_tenant_shell)
    legacy = not v3

    show_mission = v3 and bool(policy.get("show_mission_strip", True))
    if show_mission and policy.get("hide_mission_strip_after_launch") and school_has_launched(
        request
    ):
        show_mission = False

    return {
        "txp_show_mission_strip": show_mission,
        "txp_show_page_explain_strip": legacy or (
            v3 and bool(policy.get("show_legacy_explain_strip"))
        ),
        "txp_show_security_posture_inline": legacy or (
            v3 and bool(policy.get("show_security_posture_inline"))
        ),
        "txp_show_mfa_nudge": legacy or (v3 and bool(policy.get("show_mfa_nudge"))),
        "txp_show_next_action_strip": legacy or (
            v3 and bool(policy.get("show_next_action_strip"))
        ),
        "txp_show_community_band": (legacy and True) or (
            v3 and bool(policy.get("show_community_band_on_v3"))
        ),
        "txp_show_newsletter_band": (legacy and True) or (
            v3 and bool(policy.get("show_newsletter_band_on_v3"))
        ),
        "txp_show_proactive_help_nudge": legacy or (
            v3 and bool(policy.get("show_proactive_help_nudge"))
        ),
        "txp_show_lifecycle_concierge": legacy or (
            v3 and bool(policy.get("show_lifecycle_concierge"))
        ),
        "txp_show_kb_ai_panel": legacy or (v3 and bool(policy.get("show_kb_ai_panel"))),
        "txp_show_legacy_ai_copilot_dock": legacy or (
            v3 and bool(policy.get("show_legacy_ai_copilot_dock"))
        ),
        "txp_show_first_run_zero_state": legacy
        or _chrome_legacy_or_v3_opt(
            policy, "show_first_run_zero_state_on_v3", v3=v3, legacy=legacy
        ),
        "txp_show_smart_action_hub": legacy
        or _chrome_legacy_or_v3_opt(policy, "show_smart_action_hub_on_v3", v3=v3, legacy=legacy),
        "txp_show_portal_chathead": legacy
        or _chrome_legacy_or_v3_opt(policy, "show_portal_chathead_on_v3", v3=v3, legacy=legacy),
        "txp_show_header_home_link": legacy
        or _chrome_legacy_or_v3_opt(policy, "show_header_home_link_on_v3", v3=v3, legacy=legacy),
        "txp_show_workspace_os_header": legacy
        or _chrome_legacy_or_v3_opt(
            policy, "show_workspace_os_header_on_v3", v3=v3, legacy=legacy
        ),
        "txp_show_operator_console_strip": legacy
        or _chrome_legacy_or_v3_opt(
            policy, "show_operator_console_strip_on_v3", v3=v3, legacy=legacy
        ),
        "txp_show_os_status_strip": legacy
        or _chrome_legacy_or_v3_opt(policy, "show_os_status_strip_on_v3", v3=v3, legacy=legacy),
        "txp_show_zero_click_command_strip": legacy
        or _chrome_legacy_or_v3_opt(
            policy, "show_zero_click_command_strip_on_v3", v3=v3, legacy=legacy
        ),
        "txp_show_dashboard_stats_cards": legacy
        or _chrome_legacy_or_v3_opt(
            policy, "show_dashboard_stats_cards_on_v3", v3=v3, legacy=legacy
        ),
        "txp_show_legacy_sidebar_user_header": legacy
        or _chrome_legacy_or_v3_opt(
            policy, "show_legacy_sidebar_user_header_on_v3", v3=v3, legacy=legacy
        ),
        "txp_setup_surface_enabled": bool(policy.get("setup_surface_enabled", True)),
    }


def nav_sidebar_from_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": True,
        "default_mode": "normal",
        "default_width": policy.get("sidebar_default_width", _SIDEBAR_DEFAULT_WIDTH),
        "min_width": policy.get("sidebar_min_width", _SIDEBAR_MIN_WIDTH),
        "max_width": policy.get("sidebar_max_width", _SIDEBAR_MAX_WIDTH),
        "rail_width": policy.get("sidebar_rail_width", _SIDEBAR_RAIL_WIDTH),
    }


def user_may_configure_tenant_experience(user: Any) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    checker = getattr(user, "has_feature_permission", None)
    if not callable(checker):
        return False
    return bool(checker("settings.manage") or checker("settings.feature_control"))


def filter_setup_wizard_stages(
    stages_payload: dict[str, Any] | None,
    *,
    hidden_keys: list[str],
) -> dict[str, Any] | None:
    if not stages_payload or not hidden_keys:
        return stages_payload
    hidden = {key.strip().lower() for key in hidden_keys if key}
    stages = stages_payload.get("stages")
    if not isinstance(stages, list):
        return stages_payload
    filtered = []
    for stage in stages:
        if not isinstance(stage, dict):
            filtered.append(stage)
            continue
        stage_key = str(stage.get("key") or stage.get("slug") or "").strip().lower()
        if stage_key and stage_key in hidden:
            continue
        wizards = stage.get("wizards")
        if isinstance(wizards, list):
            stage = dict(stage)
            stage["wizards"] = [
                wiz
                for wiz in wizards
                if str((wiz or {}).get("key") or (wiz or {}).get("slug") or "")
                .strip()
                .lower()
                not in hidden
            ]
        filtered.append(stage)
    out = dict(stages_payload)
    out["stages"] = filtered
    return out


def persist_tenant_experience_policy(site: Any, policy: dict[str, Any]) -> None:
    """Merge policy into cockpit_payload.tenant_experience_policy."""
    payload = getattr(site, "cockpit_payload", None) or {}
    if not isinstance(payload, dict):
        payload = {}
    merged_payload = dict(payload)
    merged_payload["tenant_experience_policy"] = policy
    type(site).set_cockpit_payload(merged_payload)


def apply_and_persist_experience_preset(
    site: Any,
    preset_id: str,
    *,
    role_bucket: str | None = None,
) -> dict[str, Any]:
    """One-click preset apply (Shopify theme pattern)."""
    from apps.siteconfig.tenant_experience_presets import (
        ROLE_PRESET_INHERIT,
        apply_experience_preset,
        apply_role_overlay,
        experience_policy_role_bucket,
    )

    if role_bucket and str(role_bucket).strip().lower() not in {"", "school", "tenant"}:
        policy = resolve_tenant_experience_policy(None)
        policy = apply_role_overlay(
            policy,
            role_bucket=str(role_bucket),
            preset_id=preset_id,
        )
    else:
        policy = apply_experience_preset(preset_id)
    persist_tenant_experience_policy(site, policy)
    return policy


def portal_experience_preset_ui_context(
    request: HttpRequest, policy: dict[str, Any], *, post_url: str
) -> dict[str, Any]:
    """Template context for preset card row."""
    from apps.siteconfig.tenant_experience_presets import (
        EXPERIENCE_PRESET_CHOICES,
        ROLE_PRESET_BUCKETS,
        experience_policy_role_bucket,
        preset_catalog,
    )

    active = str(policy.get("experience_preset") or "custom")
    labels = dict(EXPERIENCE_PRESET_CHOICES)
    role_rows = []
    role_presets = policy.get("role_experience_presets") or {}
    for bucket, meta in ROLE_PRESET_BUCKETS.items():
        preset_id = str(role_presets.get(bucket) or "inherit")
        role_rows.append(
            {
                "bucket": bucket,
                "label": meta["label"],
                "preset_id": preset_id,
                "preset_label": labels.get(preset_id, preset_id.replace("_", " ").title()),
            }
        )
    return {
        "portal_experience_presets": preset_catalog(),
        "portal_experience_active_preset": active,
        "portal_experience_active_preset_label": labels.get(
            active, active.replace("_", " ").title()
        ),
        "portal_experience_preset_post_url": post_url,
        "portal_role_experience_presets": role_rows,
    }


def parse_tenant_experience_policy_from_post(post: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse flat ``txp_*`` POST keys into a stored policy dict."""
    from django import forms
    from django.core.exceptions import ValidationError

    from apps.siteconfig.forms_cockpit import (
        CockpitPayloadForm,
        build_tenant_experience_policy_from_cleaned,
    )
    from apps.siteconfig.tenant_experience_presets import (
        PRESET_CUSTOM,
        apply_experience_preset,
        merge_manual_fields_onto_policy,
    )

    cleaned: dict[str, Any] = {}
    errors: list[str] = []
    field_names = getattr(CockpitPayloadForm, "TENANT_EXPERIENCE_POLICY_FIELDS", ())
    for name in field_names:
        field = CockpitPayloadForm.base_fields.get(name)
        if field is None:
            continue
        if isinstance(field, forms.BooleanField):
            cleaned[name] = name in post
            continue
        raw = post.get(name)
        if raw in (None, "") and not field.required:
            cleaned[name] = field.initial if field.initial is not None else ""
            continue
        try:
            cleaned[name] = field.clean(raw)
        except ValidationError as exc:
            errors.extend(exc.messages)
    if errors:
        return None, errors
    preset = str(cleaned.get("txp_experience_preset") or PRESET_CUSTOM).strip().lower()
    if preset and preset != PRESET_CUSTOM:
        policy = merge_manual_fields_onto_policy(apply_experience_preset(preset), cleaned)
    else:
        policy = build_tenant_experience_policy_from_cleaned(cleaned)
    return policy, []


AI_MODE_CHOICES = (
    ("inherit", _("Inherit school AI runtime setting")),
    ("force_on", _("Force on")),
    ("force_off", _("Force off")),
)

__all__ = [
    "AI_MODE_CHOICES",
    "apply_and_persist_experience_preset",
    "compute_weighted_experience_score",
    "derive_chrome_flags",
    "experience_score_band",
    "filter_setup_wizard_stages",
    "nav_sidebar_from_policy",
    "parse_tenant_experience_policy_from_post",
    "persist_tenant_experience_policy",
    "portal_experience_preset_ui_context",
    "resolve_ai_copilot_rail_policy_enabled",
    "resolve_ai_layer_strip_enabled",
    "resolve_tenant_experience_policy",
    "role_home_legacy_mode_active",
    "school_has_launched",
    "tenant_experience_policy_defaults",
    "use_v3_shell_for_request",
    "user_may_configure_tenant_experience",
]


def resolve_ai_layer_strip_enabled(request: HttpRequest, *, runtime_enabled: bool) -> bool:
    mode = str(
        resolve_tenant_experience_policy(request).get("ai_layer_strip_mode") or "inherit"
    ).lower()
    if mode == "force_on":
        return True
    if mode == "force_off":
        return False
    return runtime_enabled


def resolve_ai_copilot_rail_policy_enabled(request: HttpRequest, *, backend_enabled: bool) -> bool:
    mode = str(
        resolve_tenant_experience_policy(request).get("ai_copilot_rail_mode") or "inherit"
    ).lower()
    if mode == "force_on":
        return True
    if mode == "force_off":
        return False
    return backend_enabled
