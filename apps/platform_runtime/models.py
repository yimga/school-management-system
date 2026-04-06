"""
Phase 10 — 1.2: Runtime defaults (state-safe migration from the siteconfig tenant settings row).
Singleton row holds JSON snapshot of tenant-affecting settings; get_effective_site_settings
reads from here when present, falling back to that singleton for file fields and legacy paths.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


def _invalidate_effective_site_settings_cache():
    """Called when RuntimeDefaults is saved so get_effective_site_settings sees new values."""
    try:
        from apps.platform_runtime.helpers import (
            invalidate_effective_site_settings_cache,
        )

        invalidate_effective_site_settings_cache()
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass


class RuntimeDefaults(models.Model):
    """
    Platform-level default settings (migrated from the siteconfig tenant settings singleton).
    id=1 singleton; payload = JSON of attribute names -> values (JSON-serializable only).
    First-class columns (see ``runtime_defaults_first_class``) override payload for those keys;
    ``sms_api_key``, ``ai_provider_api_key``, ``whatsapp_api_token``, ``marksheet_ocr_api_key``,
    ``smtp_password``, ``webhook_signing_secret``, and ``marketplace_partner_client_secret`` are first-class (not in ``payload``) so they stay out of bulk JSON
    exports while remaining excluded from Phase B marketplace snapshots.
    Backfill via migrations + sync.
    """

    payload = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    cache_rankings_interval_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="When set, resolver uses this instead of JSON payload / tenant settings singleton.",
    )
    preview_mode_enabled = models.BooleanField(null=True, blank=True)
    preview_note = models.TextField(blank=True, null=True)
    skip_theme_publish_guard = models.BooleanField(null=True, blank=True)
    sms_provider = models.CharField(max_length=64, blank=True, null=True)
    sms_sender_id = models.CharField(max_length=64, blank=True, null=True)
    email_from_address = models.CharField(max_length=255, blank=True, null=True)
    smtp_password = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="SMTP / transactional email password (marketplace_integrations). Typed column, not in JSON payload.",
    )
    whatsapp_support_number = models.CharField(max_length=64, blank=True, null=True)
    whatsapp_admissions_number = models.CharField(max_length=64, blank=True, null=True)
    enable_whatsapp_parent_portal = models.BooleanField(null=True, blank=True)
    enable_whatsapp_staff_portal = models.BooleanField(null=True, blank=True)
    marksheet_ocr_command = models.CharField(max_length=512, blank=True, null=True)
    marksheet_ocr_api_key = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="OCR / marksheet provider API key (marketplace_integrations). Typed column, not in JSON payload.",
    )
    sms_api_key = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="SMS provider API key (marketplace_integrations). Stored as a typed column, not in JSON payload.",
    )
    ai_provider_api_key = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="AI / LLM provider API key (marketplace_integrations). Typed column, not in JSON payload.",
    )
    whatsapp_api_token = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="WhatsApp Business / Cloud API access token (marketplace_integrations). Typed column, not in JSON payload.",
    )
    webhook_signing_secret = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Shared secret for signing or verifying integration webhooks (marketplace_integrations). Typed column, not in JSON payload.",
    )
    marketplace_partner_client_secret = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="OAuth-style client secret for marketplace / integration partners (marketplace_integrations). Typed column, not in JSON payload.",
    )
    company_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Public company/school display name for branded shells and comms.",
    )
    company_email = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Public contact email shown on branded surfaces.",
    )
    company_phone = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Public contact phone shown on branded surfaces.",
    )
    company_address = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Public mailing/address line used on branded pages and exports.",
    )
    company_slug = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Public short slug/identifier for links and headers.",
    )
    country = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Platform default country code/name for public context.",
    )
    region = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Platform default region label for public context.",
    )
    ministry_registration_code = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Public ministry registration identifier when applicable.",
    )
    ministry = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Platform default ministry label for public and registry-facing surfaces.",
    )
    default_region = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Platform default region profile key used by runtime/global registries.",
    )
    default_grading_scale = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Platform default grading scale key for runtime/global registries.",
    )
    admission_number_mode = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default admissions numbering mode (AUTO, MANUAL, AUTO_OR_MANUAL).",
    )
    admission_number_pattern = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="Default regex pattern for validating generated/admitted numbers.",
    )
    admission_number_strategy = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Default admissions numbering strategy key.",
    )
    admission_number_template = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Default admissions numbering template with placeholders.",
    )
    admin_portal_stats_config = models.JSONField(
        blank=True,
        null=True,
        help_text="Default admin portal statistics configuration map.",
    )
    accent_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default accent color for runtime-resolved surfaces.",
    )
    danger_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default danger color token for runtime-resolved surfaces.",
    )
    custom_css = models.TextField(
        blank=True,
        null=True,
        help_text="Default custom CSS applied on runtime-resolved branded shells.",
    )
    admin_use_site_primary = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether admin shell should reuse site primary color by default.",
    )
    default_sidebar_collapsed = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default sidebar collapse preference for shells.",
    )
    default_dashboard_view = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Default dashboard view key for runtime dashboards.",
    )
    default_refresh_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Default dashboard auto-refresh interval in seconds.",
    )
    default_widgets_per_role = models.JSONField(
        blank=True,
        null=True,
        help_text="Default per-role dashboard widgets map.",
    )
    portal_announcements = models.JSONField(
        blank=True,
        null=True,
        help_text="Default portal announcements cards list.",
    )
    portal_quick_actions = models.JSONField(
        blank=True,
        null=True,
        help_text="Default portal quick action items list.",
    )
    portal_recent_grades = models.JSONField(
        blank=True,
        null=True,
        help_text="Default portal recent grades cards list.",
    )
    portal_upcoming_assessments = models.JSONField(
        blank=True,
        null=True,
        help_text="Default portal upcoming assessments cards list.",
    )
    top_students_default_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Default top-students list limit for runtime dashboards.",
    )
    site_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Default public site/school display name.",
    )
    primary_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default primary brand color for runtime-resolved surfaces.",
    )
    success_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default success color token for runtime-resolved surfaces.",
    )
    warning_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default warning color token for runtime-resolved surfaces.",
    )
    social_links = models.JSONField(
        blank=True,
        null=True,
        help_text="Default public social links collection.",
    )
    use_dark_mode = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default dark-mode preference for runtime-resolved branded surfaces.",
    )
    use_secondary_font_for_headings = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether secondary font is used for headings by default.",
    )
    default_portal_role_dual_role = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Default dual-role portal preference key.",
    )
    enable_parent_portal = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default parent portal enabled toggle.",
    )
    enable_teacher_portal = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default teacher portal enabled toggle.",
    )
    backend_console_theme = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Default backend console theme mode.",
    )
    header_bg_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default header background color token.",
    )
    footer_bg_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default footer background color token.",
    )
    theme_brightness = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default theme brightness mode.",
    )
    theme_harmony = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Default theme harmony palette mode.",
    )
    grade_approval_enabled = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default grade-approval workflow toggle.",
    )
    grade_approval_auto_validate = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default grade-approval auto-validation toggle.",
    )
    enable_practical_assessment = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default practical-assessment toggle.",
    )
    enable_concurrent_mark_uploads = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default concurrent mark-upload toggle.",
    )
    enable_offline_mode = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default offline mode toggle.",
    )
    maintenance_mode = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default platform maintenance mode toggle.",
    )
    theme_pack = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Default theme pack slug for runtime shells.",
    )
    admin_theme_pack = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Default admin-shell theme pack slug.",
    )
    teacher_theme_pack = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Default teacher-shell theme pack slug.",
    )
    parent_theme_pack = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Default parent-shell theme pack slug.",
    )
    default_term_report_style = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Default report style key for term reports.",
    )
    default_annual_report_style = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Default report style key for annual reports.",
    )
    default_report_preview_type = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Default report preview type key.",
    )
    enable_reports_pdf = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default reports PDF generation toggle.",
    )
    reports_require_approved_grades_before_publish = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default reports publish policy requiring approved grades.",
    )
    require_mfa_all_staff = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default policy requiring MFA setup for all staff roles.",
    )
    use_promotion_rule_for_pass = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default grading policy flag for promotion-rule pass logic.",
    )
    notify_parent_welcome_email = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default toggle for parent welcome-email notification.",
    )
    reports_use_approved_grades_only = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default report policy to use approved grades only.",
    )
    report_downloads_enabled = models.BooleanField(
        null=True,
        blank=True,
        help_text="Default toggle for parent/report download surfaces (reports domain).",
    )
    requests_reminder_interval_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Default request reminder interval in hours (0 disables reminders).",
    )
    backend_feature_flags = models.JSONField(
        blank=True,
        null=True,
        help_text="Default backend feature-flag map.",
    )
    portal_features = models.JSONField(
        blank=True,
        null=True,
        help_text="Default portal feature-flag map.",
    )
    notification_channels = models.JSONField(
        blank=True,
        null=True,
        help_text="Default enabled notification channels list.",
    )
    require_mfa_roles = models.JSONField(
        blank=True,
        null=True,
        help_text="Default role codes requiring MFA setup.",
    )
    offline_sync_conflict_resolution = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Default offline-sync conflict strategy (for example: show_both).",
    )
    compliance_profile_id = models.PositiveBigIntegerField(
        blank=True,
        null=True,
        help_text="Default compliance profile pointer id (finance.ComplianceProfile).",
    )
    referral_bonus_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Default referral bonus amount.",
    )
    tagline = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Public marketing / platform tagline (short phrase).",
    )
    school_code = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Short institution code (e.g. stock ticker style) for labels and integrations.",
    )
    meta_description = models.CharField(
        max_length=320,
        blank=True,
        null=True,
        help_text="Default meta description for public marketing shells.",
    )
    branded_domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Canonical branded hostname for public links (no scheme).",
    )
    public_brand_primary_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Marketing / control-plane navbar + hero (e.g. #0f172a).",
    )
    public_brand_accent_color = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="CTAs and links on public shells (e.g. #f59e0b).",
    )

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Runtime defaults"
        verbose_name_plural = "Runtime defaults"

    @classmethod
    def get_singleton(cls) -> "RuntimeDefaults | None":
        return cls.objects.filter(pk=1).first()

    @classmethod
    def build_payload_from_site_settings(
        cls,
        site_settings,
        *,
        owners: list[str] | tuple[str, ...] | set[str] | None = None,
        exclude_owners: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> dict:
        """Build an ownership-filtered runtime payload from the legacy tenant settings singleton row."""
        from apps.platform_runtime.runtime_sync_owner_filters import (
            normalize_runtime_sync_owner_filters,
        )

        owners, exclude_owners = normalize_runtime_sync_owner_filters(
            owners,
            exclude_owners,
        )
        owner_set = set(owners or [])
        excluded = set(exclude_owners or [])
        if not owner_set:
            excluded.add("delete")
        if owner_set:
            payload: dict = {}
            for owner in owner_set:
                payload.update(
                    site_settings.owned_payload(owner=owner, exclude_owners=excluded)
                )
            return payload
        return site_settings.owned_payload(exclude_owners=excluded)

    @classmethod
    def sync_from_site_settings(
        cls,
        site_settings,
        *,
        owners: list[str] | tuple[str, ...] | set[str] | None = None,
        exclude_owners: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> tuple["RuntimeDefaults", bool]:
        """Persist a filtered RuntimeDefaults payload from the tenant settings row and return (object, created).
        Callers must pass site_settings (e.g. get_platform_site_settings_record() in commands, self on save).
        B1 allowlist shrink: no get_solo() in this module."""
        from apps.platform_runtime.runtime_sync_owner_filters import (
            normalize_runtime_sync_owner_filters,
            resolve_runtime_sync_owner_scope,
        )

        owners, exclude_owners = normalize_runtime_sync_owner_filters(
            owners,
            exclude_owners,
        )
        from apps.platform_runtime.runtime_defaults_first_class import (
            collect_first_class_values_from_site_settings,
            first_class_field_names_for_runtime_sync,
            strip_runtime_defaults_first_class_keys_from_dict,
        )
        sync_owner_scope = resolve_runtime_sync_owner_scope(owners, exclude_owners)
        owner_set = set(sync_owner_scope)
        scoped_first_class_fields = first_class_field_names_for_runtime_sync(
            sync_owner_scope
        )

        payload = cls.build_payload_from_site_settings(
            site_settings,
            owners=owners,
            exclude_owners=exclude_owners,
        )
        strip_runtime_defaults_first_class_keys_from_dict(payload)
        fc_values = collect_first_class_values_from_site_settings(
            site_settings,
            field_names=scoped_first_class_fields,
        )
        defaults: dict = {"payload": payload, **fc_values}
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults=defaults,
        )
        if not created:
            merged_payload = dict(obj.payload or {})
            for owner in owner_set:
                for field_name in site_settings.owned_field_names(owner=owner):
                    merged_payload.pop(field_name, None)
            merged_payload.update(payload)
            strip_runtime_defaults_first_class_keys_from_dict(merged_payload)
            obj.payload = merged_payload
            for fname in scoped_first_class_fields:
                setattr(obj, fname, fc_values.get(fname))
            obj.save(
                update_fields=list(scoped_first_class_fields)
                + ["payload", "updated_at"]
            )
        return obj, created

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.pk == 1:
            _invalidate_effective_site_settings_cache()


class PlatformPhaseBDomainSnapshot(models.Model):
    """
    Phase B Batches 4-13: one JSON snapshot per non-brand ownership domain.

    Rows mirror the tenant settings singleton's ``owned_payload(owner=domain)`` on save (excluding
    marketplace secret columns such as ``sms_api_key`` and ``ai_provider_api_key``).
    ``get_effective_site_settings``
    merges these after ``RuntimeDefaults`` and before ``PlatformGlobalBranding``.
    """

    domain = models.CharField(max_length=64, primary_key=True)
    payload = models.JSONField(default=dict, blank=True)
    payload_key_count = models.PositiveIntegerField(
        default=0,
        help_text="Top-level keys in payload (typed index for operator dashboards).",
    )
    payload_checksum = models.CharField(
        max_length=64,
        blank=True,
        help_text="sha256(hex) of canonical JSON — compare to live owned_payload fingerprint.",
    )
    payload_key_checksums = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map top-level payload key → sha256(hex) of that key's canonical JSON value.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_phase_b_domain_snapshot"
        verbose_name = "Phase B domain snapshot"
        verbose_name_plural = "Phase B domain snapshots"

    def __str__(self) -> str:
        return self.domain

    def refresh_payload_metadata(self) -> None:
        from apps.platform_runtime.phase_b_domain_snapshots import (
            phase_b_payload_metadata,
            phase_b_top_level_key_fingerprints,
        )

        k, h = phase_b_payload_metadata(self.payload)
        self.payload_key_count = k
        self.payload_checksum = h
        pl = self.payload if isinstance(self.payload, dict) else {}
        self.payload_key_checksums = phase_b_top_level_key_fingerprints(pl)


class PlatformReportPlatformSkuDefault(models.Model):
    """
    Singleton (pk=1): operator default report-platform SKU bundle for ``plans_entitlements`` depth.

    Surfaces in ``/api/v1/manifest.json`` under ``plan_entitlements.operator_default_report_platform_bundle``
    when set. Valid slugs match ``REPORT_PLATFORM_SKU_BUNDLES`` in ``billing_sku_registry``.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    default_bundle_slug = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="e.g. reports-standard or reports-advanced (see billing_sku_registry).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_reportplatformskudefault"
        verbose_name = "Report platform SKU default"
        verbose_name_plural = "Report platform SKU defaults"

    def __str__(self) -> str:
        return f"pk={self.pk} bundle={self.default_bundle_slug or '—'}"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        from apps.siteconfig.billing_sku_registry import REPORT_PLATFORM_SKU_BUNDLES

        if self.default_bundle_slug:
            s = str(self.default_bundle_slug).strip().lower()
            if s not in REPORT_PLATFORM_SKU_BUNDLES:
                raise ValidationError(
                    {
                        "default_bundle_slug": (
                            "Must be a known REPORT_PLATFORM_SKU bundle slug or empty."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class PlatformOperatorPlaybookLink(models.Model):
    """
    Typed operator navigation rows for migration playbooks and runbooks (runtime_operations).

    Curated in platform admin; surfaced on the super **Playbook operator hub** alongside
    live execution audit. Not part of tenant virtual keys on the siteconfig singleton.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/workflow-simulator/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="playbook",
        help_text="e.g. playbook, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorplaybooklink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator playbook link"
        verbose_name_plural = "Operator playbook links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorTruthHubLink(models.Model):
    """
    Typed operator navigation rows for the **Runtime truth hub** (runtime_operations).

    Curated in platform admin; surfaced on ``super:runtime_truth_hub`` alongside static
    playbook/automation anchors. Complements ``PlatformOperatorPlaybookLink`` (playbook hub).
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/phase-b-snapshot-diff/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="truth_hub",
        help_text="e.g. truth_hub, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatortruthhublink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator truth hub link"
        verbose_name_plural = "Operator truth hub links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorPhaseBLink(models.Model):
    """
    Typed operator navigation rows for the **Phase B snapshot diff** surface.

    Curated in platform admin; surfaced on ``super:phase_b_snapshot_diff`` alongside
    static anchors. Complements ``PlatformOperatorPlaybookLink`` and
    ``PlatformOperatorTruthHubLink``.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/runtime-truth-hub/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="phase_b",
        help_text="e.g. phase_b, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorphaseblink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator Phase B link"
        verbose_name_plural = "Operator Phase B links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorWorkflowSimulatorLink(models.Model):
    """
    Typed operator navigation rows for the **Workflow simulator** surface.

    Curated in platform admin; surfaced on ``super:workflow_simulator`` alongside
    the school/role simulation form. Complements other ``PlatformOperator*Link`` tables.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/runtime-inspector/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="workflow_simulator",
        help_text="e.g. workflow_simulator, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorworkflowsimulatorlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator workflow simulator link"
        verbose_name_plural = "Operator workflow simulator links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorSupportDashboardLink(models.Model):
    """
    Typed operator navigation rows for the **Support mission control** surface.

    Curated in platform admin; surfaced on ``super:support_dashboard`` alongside
    ticket queue and SLA widgets.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/pulse/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="support_dashboard",
        help_text="e.g. support_dashboard, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorsupportdashboardlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator support dashboard link"
        verbose_name_plural = "Operator support dashboard links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorTenantHealthLink(models.Model):
    """
    Typed operator navigation rows for the **Tenant health monitor** surface.

    Curated in platform admin; surfaced on ``super:tenant_health`` alongside
    the per-school lifecycle table.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/pulse/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="tenant_health",
        help_text="e.g. tenant_health, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatortenanthealthlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator tenant health link"
        verbose_name_plural = "Operator tenant health links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorCommandCenterLink(models.Model):
    """
    Typed operator navigation rows for the **Mission / command center** surface.

    Curated in platform admin; surfaced on ``super:command_center`` alongside
    operational queue panels.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/pulse/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="command_center",
        help_text="e.g. command_center, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorcommandcenterlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator command center link"
        verbose_name_plural = "Operator command center links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorOrchestrationWorkbenchLink(models.Model):
    """
    Typed operator navigation rows for the **Orchestration workbench** surface.

    Curated in platform admin; surfaced on ``super:orchestration_workbench`` alongside
    the runs table.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/playbook-operator-hub/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="orchestration_workbench",
        help_text="e.g. orchestration_workbench, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatororchestrationworkbenchlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator orchestration workbench link"
        verbose_name_plural = "Operator orchestration workbench links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorSuperDashboardLink(models.Model):
    """
    Typed operator navigation rows for the **Control plane home** (``super:dashboard``).

    Curated in platform admin; surfaced on ``schools/super_dashboard.html`` alongside
    mission-control cards.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/command-center/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="super_dashboard",
        help_text="e.g. super_dashboard, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorsuperdashboardlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator super dashboard link"
        verbose_name_plural = "Operator super dashboard links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorSuperSchoolsListLink(models.Model):
    """
    Typed operator navigation rows for **Schools list** (``super:schools_list``).

    Curated in platform admin; surfaced on ``schools/super_schools_list.html`` when rows exist.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/tenant-health/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="super_schools_list",
        help_text="e.g. super_schools_list, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorsuperschoolslistlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator super schools list link"
        verbose_name_plural = "Operator super schools list links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorSuperAnalyticsOverviewLink(models.Model):
    """
    Typed operator navigation rows for **Analytics overview** (``super:analytics_overview``).

    Curated in platform admin; surfaced on ``schools/super_analytics_overview.html`` when rows exist.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/usage/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="super_analytics_overview",
        help_text="e.g. super_analytics_overview, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorsuperanalyticsoverviewlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator super analytics overview link"
        verbose_name_plural = "Operator super analytics overview links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorPlatformHubLink(models.Model):
    """
    Typed operator navigation rows for **Platform operator hub** (``super:platform_operator_hub``).

    Curated in platform admin; surfaced on ``schools/super_platform_operator_hub.html`` when rows exist.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/command-center/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="super_platform_operator_hub",
        help_text="e.g. super_platform_operator_hub, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorplatformhublink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator platform hub link"
        verbose_name_plural = "Operator platform hub links"

    def __str__(self) -> str:
        return self.label


class PlatformOperatorMigrationCloudLink(models.Model):
    """
    Typed operator navigation rows for **Migration cloud** (``super:migration_cloud``).

    Curated in platform admin; surfaced on ``schools/super_migration_cloud.html`` when rows exist.
    """

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    href = models.CharField(
        max_length=512,
        help_text="Relative path (e.g. /super/migration/registry/) or absolute URL.",
    )
    category = models.CharField(
        max_length=32,
        blank=True,
        default="super_migration_cloud",
        help_text="e.g. super_migration_cloud, admin, runbook",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatormigrationcloudlink"
        ordering = ("sort_order", "slug")
        verbose_name = "Operator migration cloud link"
        verbose_name_plural = "Operator migration cloud links"

    def __str__(self) -> str:
        return self.label


class PlatformIntegrationWebhookEvent(models.Model):
    """
    Inbound integration webhook receipts (HMAC verified with
    ``RuntimeDefaults.webhook_signing_secret`` / ``get_effective_site_settings``).

    Stores metadata only (no raw body) for operator audit and incident response.
    """

    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    verified = models.BooleanField(default=False, db_index=True)
    event_type = models.CharField(max_length=64, blank=True, default="")
    body_sha256 = models.CharField(max_length=64, blank=True, default="")
    client_ip = models.CharField(max_length=45, blank=True, default="")

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_integration_webhook_event"
        verbose_name = "Integration webhook event"
        verbose_name_plural = "Integration webhook events"
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"{self.received_at:%Y-%m-%d %H:%M} verified={self.verified}"


class AIActionAuditLog(models.Model):
    """
    Phase 10 — 10.8: AI action audit trail.
    One row per AI-invoked action (e.g. suggestion accepted, content generated); for compliance and debugging.
    """

    action_type = models.CharField(max_length=80, db_index=True)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "AI action audit log"
        verbose_name_plural = "AI action audit logs"
        ordering = ["-created_at"]


class PlatformEventLog(models.Model):
    """
    Append-only outbox for emit_platform_event (§0.3 Pillar 5 — event-driven baseline).
    Enables replay, analytics, and future webhook fan-out without losing events at log-only phase.
    """

    event_type = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    tenant_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    school_id = models.CharField(max_length=40, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(
        max_length=128, blank=True, default="", db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Platform event log"
        verbose_name_plural = "Platform event logs"
        ordering = ["-created_at"]


class FleetGovernedChange(models.Model):
    """
    WHATS_LEFT §2.1 — auditable fleet change record (thin slice).

    State machine coordinates operator intent; execution uses existing apply UIs
    (staged activation, package rollout, feature control, etc.) linked via ``apply_surface_url``.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
        SCHEDULED = "SCHEDULED", "Scheduled"
        APPLYING = "APPLYING", "Applying"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    title = models.CharField(max_length=200, blank=True, default="")
    change_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Logical class of change, e.g. PACKAGE_ROLLOUT, FEATURE_FLAG.",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    scope = models.JSONField(
        default=dict,
        blank=True,
        help_text="Target scope (tenant ids, segments, school keys, etc.).",
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Apply hints / parameters for the operator completing work downstream.",
    )
    apply_surface_url = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Named URL path or absolute link to the apply UI (staged activation, rollout, …).",
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fleet_governed_changes_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fleet_governed_changes_approved",
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Fleet governed change"
        verbose_name_plural = "Fleet governed changes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        label = (self.title or "").strip() or self.change_type or "change"
        return f"{label} ({self.pk})" if self.pk else label
