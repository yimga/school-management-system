"""
First-class columns on ``RuntimeDefaults`` (platform_runtime-owned).

These keys are **not** duplicated in ``RuntimeDefaults.payload`` when present; they are
read from typed columns and override payload in ``get_effective_site_settings`` merge
order. Marketplace secrets (``sms_api_key``, ``ai_provider_api_key``, ``whatsapp_api_token``,
``marksheet_ocr_api_key``, ``smtp_password``, ``webhook_signing_secret``,
``marketplace_partner_client_secret``)
are first-class (still excluded from Phase B marketplace JSON snapshots). Additional
marketplace **secrets** need a new tenant site-settings virtual key + migration **0039+** using
the same pattern as **0029**–**0037**. Static parity (dict / strip list / this tuple / model)
is enforced by ``scripts/verify_marketplace_integration_first_class_parity.py``.

See ``RuntimeDefaults.sync_from_site_settings`` and ``_build_platform_site_settings_base``.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

# Field names on RuntimeDefaults model (must match migration + model definition).
RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES: tuple[str, ...] = (
    "company_name",
    "company_email",
    "company_phone",
    "company_address",
    "company_slug",
    "country",
    "region",
    "ministry_registration_code",
    "ministry",
    "default_region",
    "default_grading_scale",
    "admission_number_mode",
    "admission_number_pattern",
    "admission_number_strategy",
    "admission_number_template",
    "admin_portal_stats_config",
    "accent_color",
    "danger_color",
    "custom_css",
    "admin_use_site_primary",
    "default_sidebar_collapsed",
    "default_dashboard_view",
    "default_refresh_rate",
    "default_widgets_per_role",
    "portal_announcements",
    "portal_quick_actions",
    "portal_recent_grades",
    "portal_upcoming_assessments",
    "top_students_default_limit",
    "site_name",
    "primary_color",
    "success_color",
    "warning_color",
    "social_links",
    "use_dark_mode",
    "use_secondary_font_for_headings",
    "default_portal_role_dual_role",
    "enable_parent_portal",
    "enable_teacher_portal",
    "enable_student_portal",
    "backend_console_theme",
    "header_bg_color",
    "footer_bg_color",
    "theme_brightness",
    "theme_harmony",
    # Theme system v2 (2026-05-12, Phase J end-to-end): tenant-configurable
    # single-accent gradient + warm-graphite alternate palette.
    "brand_gradient_end",
    "brand_gradient_angle",
    "neutral_palette",
    # 2026-05-12 carried-forward: companion dark logo for `[data-resolved-theme="dark"]`.
    "site_logo_dark_url",
    # v2.42 (2026-05-15) — warm-bright aesthetic configurability closeout.
    "aesthetic_profile",
    "aesthetic_surface_bg",
    "aesthetic_surface_canvas",
    "aesthetic_text_primary",
    "aesthetic_accent_warm",
    "aesthetic_accent_success",
    "aesthetic_accent_danger",
    "grade_approval_enabled",
    "grade_approval_auto_validate",
    "enable_practical_assessment",
    "enable_concurrent_mark_uploads",
    "enable_offline_mode",
    "maintenance_mode",
    "theme_pack",
    "admin_theme_pack",
    "teacher_theme_pack",
    "parent_theme_pack",
    "default_term_report_style",
    "default_annual_report_style",
    "default_report_preview_type",
    "enable_reports_pdf",
    "reports_require_approved_grades_before_publish",
    "require_mfa_all_staff",
    "use_promotion_rule_for_pass",
    "notify_parent_welcome_email",
    "reports_use_approved_grades_only",
    "report_downloads_enabled",
    "requests_reminder_interval_hours",
    "backend_feature_flags",
    "portal_features",
    "notification_channels",
    "require_mfa_roles",
    "mfa_enforcement_mode",
    "mfa_grace_period_days",
    "offline_sync_conflict_resolution",
    "ai_mode",
    "compliance_profile_id",
    "referral_bonus_amount",
    "tagline",
    "school_code",
    "meta_description",
    "branded_domain",
    "public_brand_primary_color",
    "public_brand_accent_color",
    "public_brand_logo_url",
    "public_brand_logo_dark_url",
    "public_brand_favicon_url",
    "cache_rankings_interval_minutes",
    "preview_mode_enabled",
    "preview_note",
    "skip_theme_publish_guard",
    "sms_provider",
    "sms_sender_id",
    "email_from_address",
    "smtp_password",
    "whatsapp_support_number",
    "whatsapp_admissions_number",
    "enable_whatsapp_parent_portal",
    "enable_whatsapp_staff_portal",
    "marksheet_ocr_command",
    "marksheet_ocr_api_key",
    "ai_provider_api_key",
    "sms_api_key",
    "whatsapp_api_token",
    "webhook_signing_secret",
    "marketplace_partner_client_secret",
)

# Empty string on these means "no platform default" (do not beat RuntimeDefaults.payload).
RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "company_name",
        "company_email",
        "company_phone",
        "company_address",
        "company_slug",
        "country",
        "region",
        "ministry_registration_code",
        "ministry",
        "default_region",
        "default_grading_scale",
        "admission_number_mode",
        "admission_number_pattern",
        "admission_number_strategy",
        "admission_number_template",
        "accent_color",
        "danger_color",
        "custom_css",
        "default_dashboard_view",
        "site_name",
        "primary_color",
        "success_color",
        "warning_color",
        "default_portal_role_dual_role",
        "backend_console_theme",
        "header_bg_color",
        "footer_bg_color",
        "theme_brightness",
        "theme_harmony",
        # Theme system v2 (2026-05-12, Phase J end-to-end).
        "brand_gradient_end",
        "brand_gradient_angle",
        "neutral_palette",
        "site_logo_dark_url",
        "theme_pack",
        "admin_theme_pack",
        "teacher_theme_pack",
        "parent_theme_pack",
        "default_term_report_style",
        "default_annual_report_style",
        "default_report_preview_type",
        "offline_sync_conflict_resolution",
        "mfa_enforcement_mode",
        "ai_mode",
        "tagline",
        "school_code",
        "meta_description",
        "branded_domain",
        "public_brand_primary_color",
        "public_brand_accent_color",
        "public_brand_logo_url",
        "public_brand_logo_dark_url",
        "public_brand_favicon_url",
        "preview_note",
        "sms_provider",
        "sms_sender_id",
        "email_from_address",
        "smtp_password",
        "whatsapp_support_number",
        "whatsapp_admissions_number",
        "marksheet_ocr_command",
        "marksheet_ocr_api_key",
        "ai_provider_api_key",
        "sms_api_key",
        "whatsapp_api_token",
        "webhook_signing_secret",
        "marketplace_partner_client_secret",
    }
)


def runtime_defaults_first_class_string_is_blank(val: object) -> bool:
    return isinstance(val, str) and not val.strip()


def strip_runtime_defaults_first_class_keys_from_dict(d: dict) -> None:
    """Remove first-class keys from a payload dict (in-place)."""
    for k in RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES:
        d.pop(k, None)


@lru_cache(maxsize=1)
def _domain_ownership_classifier():
    try:
        from apps.siteconfig.domain_ownership import classify_site_settings_field

        return classify_site_settings_field
    except ModuleNotFoundError:
        domain_ownership = (
            Path(__file__).resolve().parents[1] / "siteconfig" / "domain_ownership.py"
        )
        spec = importlib.util.spec_from_file_location(
            "siteconfig_domain_ownership_runtime_defaults_first_class",
            domain_ownership,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load {domain_ownership}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.classify_site_settings_field


def first_class_field_names_for_runtime_sync(
    owners: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Return RuntimeDefaults first-class fields within the effective owner scope."""
    if owners is None:
        return RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES

    owner_set = set(owners)
    return tuple(
        field_name
        for field_name in RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES
        if _domain_ownership_classifier()(field_name) in owner_set
    )


def collect_first_class_values_from_site_settings(
    site_settings,
    *,
    field_names: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Snapshot current effective values from the legacy tenant site-settings façade (virtual + column)."""
    out: dict[str, object] = {}
    for k in field_names or RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES:
        v = getattr(site_settings, k, None)
        if k in RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES:
            if runtime_defaults_first_class_string_is_blank(v):
                v = None
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# Per-tenant runtime-defaults override shim — Unified Wizard Framework
# ---------------------------------------------------------------------------
#
# ``RuntimeDefaults`` is a global singleton (no ``school`` FK). Per-tenant
# overrides layer in via ``school.settings`` and are merged on top of the
# singleton inside ``get_effective_site_settings``. This shim is the canonical
# write path for setup-studio wizard answers that target a RuntimeDefaults
# field — instead of mutating the singleton (which would clobber every tenant),
# it lands the override in ``school.settings["runtime_defaults"][<field>]``.

# Wizard-driven brand/typography keys are not on the singleton today; they
# are persisted only via per-tenant overrides + read by the effective-settings
# merger. Add new keys here when wizards start writing them.
_WIZARD_RUNTIME_DEFAULT_KEYS: frozenset[str] = frozenset({
    "brand_palette_key",
    "brand_primary_color",
    "brand_secondary_color",
    "brand_type_scale_anchor",
    # Intelligent-sidebar defaults (read via the SITE façade → emitted as nav
    # data-attributes; per-tenant override lands in school.settings). Payload-
    # backed (no first-class column / migration); owned by brand_experience via
    # the "sidebar_" prefix in EXACT/PREFIX field ownership.
    "sidebar_intelligence",
    "sidebar_search",
    "sidebar_adaptive_order",
    "sidebar_density",
    # Unified ⌘K command-palette engine defaults (read via the SITE façade →
    # emitted as #rmc-cmdk data-attributes; per-tenant override lands in
    # school.settings). Payload-backed (no migration); owned by brand_experience
    # via the "command_palette_" prefix in field ownership.
    "command_palette_intelligence",
    "command_palette_fuzzy",
    "command_palette_adaptive",
    "command_palette_federate_sidebar",
    # Shared table-intelligence engine defaults (read via SITE façade → emitted
    # in the #rmc-tables-config island; per-tenant override in school.settings).
    # Payload-backed (no migration); owned by brand_experience via "table_".
    "table_intelligence",
    "table_filter",
    "table_sort",
    "table_columns",
    "table_export",
    "table_density",
    # Dashboard-intelligence engine defaults (read via SITE façade → emitted in
    # the #rmc-dashboard-config island; per-user reorder/hide/density persist in
    # DashboardUserPreference). Payload-backed (no migration); the "dashboard_"
    # prefix is already a shadow-key owner (runtime_blueprints).
    "dashboard_intelligence",
    "dashboard_reorder",
    "dashboard_adaptive",
    "dashboard_density",
    # Form-intelligence engine defaults (read via SITE façade → emitted in the
    # #rmc-forms-config island; the engine auto-attaches to every POST form).
    # Payload-backed (no migration); owned by brand_experience via "form_".
    "form_intelligence",
    "form_unsaved_guard",
    "form_pending",
    "form_validation",
    "form_section_nav",
    # Empty-state intelligence engine defaults (read via SITE façade → emitted in
    # the #rmc-empty-config island + the first-run zero-state card). Payload-backed
    # (no migration); owned by brand_experience via the "empty_" prefix.
    "empty_intelligence",
    "empty_table_filter",
    "empty_table_data",
    "empty_adopt",
    "empty_first_run",
    # Loading-intelligence engine defaults (read via SITE façade → emitted in the
    # #rmc-loading-config island). Payload-backed (no migration); owned by
    # brand_experience via the "loading_" prefix.
    "loading_intelligence",
    "loading_actions",
    "loading_skeletons",
    # Notification-intelligence engine defaults (read via SITE façade → emitted
    # in the #rmc-notification-config island). Payload-backed (no migration);
    # owned by brand_experience via the "notify_" prefix.
    "notify_intelligence",
    "notify_bell_preview",
    "notify_inline_actions",
    "notify_toast_sync",
    # Modal-intelligence engine defaults (read via SITE façade → emitted in the
    # #rmc-modal-config island). Payload-backed (no migration); owned by
    # brand_experience via the "modal_" prefix.
    "modal_intelligence",
    "modal_confirm",
    "modal_danger_guard",
    # Detail-intelligence engine defaults (read via SITE façade → emitted in the
    # #rmc-detail-config island). Payload-backed (no migration); owned by
    # brand_experience via the "detail_" prefix.
    "detail_intelligence",
    "detail_copy",
    "detail_actionable",
    "detail_empty_fields",
    "detail_section_nav",
})


def set_runtime_default(*, school, field: str, value):
    """Persist a per-tenant runtime-default override into ``school.settings``.

    ``field`` must be a recognized key: either present on the ``RuntimeDefaults``
    singleton (``RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES``) or an explicit
    wizard-driven key (``_WIZARD_RUNTIME_DEFAULT_KEYS``). Unknown keys log a
    warning and no-op.

    Returns ``True`` on state change, ``False`` on no-op.
    """
    import logging
    logger = logging.getLogger(__name__)

    if school is None or not field:
        return False
    if getattr(school, "pk", None) is None:
        return False
    if (
        field not in RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES
        and field not in _WIZARD_RUNTIME_DEFAULT_KEYS
    ):
        logger.warning("set_runtime_default: unknown field %r (no whitelist match)", field)
        return False

    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}
    rd_bucket = settings.get("runtime_defaults") or {}
    if not isinstance(rd_bucket, dict):
        rd_bucket = {}

    if rd_bucket.get(field) == value:
        return False
    rd_bucket[field] = value
    settings["runtime_defaults"] = rd_bucket

    try:
        school.settings = settings
        school.save(update_fields=["settings"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("set_runtime_default: save failed: %s", exc)
        return False
    return True
