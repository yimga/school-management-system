from django import forms
from django.contrib import admin
from django.contrib.admin.filters import DateFieldListFilter
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin

from config.admin import register_platform_admin

from .fleet_apply_surfaces import (
    fleet_apply_surface_preset_choices,
    resolve_fleet_apply_surface,
)
from .models import (
    EventWebhookDelivery,
    EventWebhookSubscription,
    FleetGovernedChange,
    PilotDefect,
    PlatformEventLog,
    PlatformIntegrationWebhookEvent,
    PlatformOperatorCommandCenterLink,
    PlatformOperatorMigrationCloudLink,
    PlatformOperatorOrchestrationWorkbenchLink,
    PlatformOperatorPlatformHubLink,
    PlatformOperatorSuperDashboardLink,
    PlatformOperatorSuperAnalyticsOverviewLink,
    PlatformOperatorSuperSchoolsListLink,
    PlatformOperatorPhaseBLink,
    PlatformOperatorPlaybookLink,
    PlatformOperatorSupportDashboardLink,
    PlatformOperatorTenantHealthLink,
    PlatformOperatorTruthHubLink,
    PlatformOperatorWorkflowSimulatorLink,
    PlatformPhaseBDomainSnapshot,
    PlatformReportPlatformSkuDefault,
    RuntimeDefaults,
)
from .runtime_defaults_first_class import strip_runtime_defaults_first_class_keys_from_dict


class RuntimeDefaultsBrandForm(forms.ModelForm):
    """First-class columns map to model fields; ``save_model`` strips those keys from JSON payload."""

    class Meta:
        model = RuntimeDefaults
        fields = [
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
            "offline_sync_conflict_resolution",
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
            "webhook_signing_secret",
            "marketplace_partner_client_secret",
            "whatsapp_support_number",
            "whatsapp_admissions_number",
            "enable_whatsapp_parent_portal",
            "enable_whatsapp_staff_portal",
            "marksheet_ocr_command",
            "marksheet_ocr_api_key",
            "ai_provider_api_key",
            "sms_api_key",
            "whatsapp_api_token",
            "payload",
        ]
        widgets = {
            "public_brand_primary_color": forms.TextInput(
                attrs={"placeholder": "#0f172a"}
            ),
            "public_brand_accent_color": forms.TextInput(
                attrs={"placeholder": "#f59e0b"}
            ),
            "public_brand_logo_url": forms.URLInput(
                attrs={"placeholder": "https://cdn.example.com/brand/logo.png"}
            ),
            "public_brand_logo_dark_url": forms.URLInput(
                attrs={"placeholder": "https://cdn.example.com/brand/logo-dark.png"}
            ),
            "public_brand_favicon_url": forms.URLInput(
                attrs={"placeholder": "https://cdn.example.com/brand/favicon.png"}
            ),
            "sms_api_key": forms.PasswordInput(
                render_value=True,
                attrs={"autocomplete": "off"},
            ),
            "marksheet_ocr_api_key": forms.PasswordInput(
                render_value=True,
                attrs={"autocomplete": "off"},
            ),
            "smtp_password": forms.PasswordInput(
                render_value=True,
                attrs={"autocomplete": "off"},
            ),
            "webhook_signing_secret": forms.PasswordInput(
                render_value=True,
                attrs={"autocomplete": "off"},
            ),
            "marketplace_partner_client_secret": forms.PasswordInput(
                render_value=True,
                attrs={"autocomplete": "off"},
            ),
        }


class RuntimeDefaultsAdmin(ModelAdmin):
    form = RuntimeDefaultsBrandForm
    list_display = ["id", "updated_at"]
    readonly_fields = ["updated_at"]
    fieldsets = (
        (
            "Platform identity & public brand",
            {
                "fields": (
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
                    "tagline",
                    "school_code",
                    "meta_description",
                    "branded_domain",
                    "public_brand_primary_color",
                    "public_brand_accent_color",
                    "public_brand_logo_url",
                    "public_brand_logo_dark_url",
                    "public_brand_favicon_url",
                )
            },
        ),
        (
            "Runtime blueprint defaults (domain_ownership: runtime_blueprints)",
            {
                "description": (
                    "Admission defaults, admin stats JSON, and portal/dashboard shell defaults "
                    "owned by the runtime_blueprints slice."
                ),
                "fields": (
                    "admission_number_mode",
                    "admission_number_pattern",
                    "admission_number_strategy",
                    "admission_number_template",
                    "admin_portal_stats_config",
                    "default_dashboard_view",
                    "default_refresh_rate",
                    "default_widgets_per_role",
                    "portal_announcements",
                    "portal_quick_actions",
                    "portal_recent_grades",
                    "portal_upcoming_assessments",
                    "top_students_default_limit",
                ),
            },
        ),
        (
            "Brand & theme (domain_ownership: brand_experience)",
            {
                "description": (
                    "Typed columns mirroring brand_experience ownership; theme packs and "
                    "Platform global branding remain the deep surface for media."
                ),
                "fields": (
                    "accent_color",
                    "danger_color",
                    "custom_css",
                    "admin_use_site_primary",
                    "default_sidebar_collapsed",
                    "site_name",
                    "primary_color",
                    "success_color",
                    "warning_color",
                    "social_links",
                    "use_dark_mode",
                    "use_secondary_font_for_headings",
                    "backend_console_theme",
                    "header_bg_color",
                    "footer_bg_color",
                    "theme_brightness",
                    "theme_harmony",
                    "theme_pack",
                    "admin_theme_pack",
                    "teacher_theme_pack",
                    "parent_theme_pack",
                ),
            },
        ),
        (
            "Platform operations (domain_ownership: safe_platform_default)",
            {
                "fields": ("maintenance_mode",),
            },
        ),
        (
            "Policies & portal gates (domain_ownership: policies_rules)",
            {
                "description": (
                    "Typed defaults for policy-heavy toggles. Prefer Feature Control for "
                    "audited toggles where product exposes it; JSON blobs here remain the "
                    "platform default floor."
                ),
                "fields": (
                    "default_portal_role_dual_role",
                    "enable_parent_portal",
                    "enable_teacher_portal",
                    "grade_approval_enabled",
                    "grade_approval_auto_validate",
                    "enable_practical_assessment",
                    "enable_concurrent_mark_uploads",
                    "enable_offline_mode",
                    "require_mfa_all_staff",
                    "use_promotion_rule_for_pass",
                    "notify_parent_welcome_email",
                    "requests_reminder_interval_hours",
                    "backend_feature_flags",
                    "portal_features",
                    "notification_channels",
                    "require_mfa_roles",
                    "offline_sync_conflict_resolution",
                    "compliance_profile_id",
                    "referral_bonus_amount",
                ),
            },
        ),
        (
            "Reports defaults (domain_ownership: reports)",
            {
                "fields": (
                    "default_term_report_style",
                    "default_annual_report_style",
                    "default_report_preview_type",
                    "enable_reports_pdf",
                    "reports_require_approved_grades_before_publish",
                    "reports_use_approved_grades_only",
                    "report_downloads_enabled",
                ),
            },
        ),
        (
            "Platform preview",
            {
                "fields": (
                    "preview_mode_enabled",
                    "preview_note",
                    "skip_theme_publish_guard",
                ),
            },
        ),
        (
            "Integrations (non-secret)",
            {
                "fields": (
                    "sms_provider",
                    "sms_sender_id",
                    "email_from_address",
                    "whatsapp_support_number",
                    "whatsapp_admissions_number",
                    "enable_whatsapp_parent_portal",
                    "enable_whatsapp_staff_portal",
                    "marksheet_ocr_command",
                ),
                "description": "Provider identifiers and non-secret integration defaults.",
            },
        ),
        (
            "Integrations (secret)",
            {
                "fields": (
                    "ai_provider_api_key",
                    "sms_api_key",
                    "whatsapp_api_token",
                    "marksheet_ocr_api_key",
                    "smtp_password",
                    "webhook_signing_secret",
                    "marketplace_partner_client_secret",
                ),
                "description": "Stored as typed columns (not duplicated in JSON payload); excluded from Phase B marketplace snapshots.",
            },
        ),
        ("Owned runtime fields", {"fields": ("cache_rankings_interval_minutes",)}),
        ("Payload (advanced)", {"fields": ("payload",)}),
    )

    def save_model(self, request, obj, form, change):
        payload = dict(obj.payload or {})
        strip_runtime_defaults_first_class_keys_from_dict(payload)
        obj.payload = payload
        super().save_model(request, obj, form, change)


register_platform_admin(RuntimeDefaults, RuntimeDefaultsAdmin)


class PlatformOperatorPlaybookLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(PlatformOperatorPlaybookLink, PlatformOperatorPlaybookLinkAdmin)


class PlatformOperatorTruthHubLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(PlatformOperatorTruthHubLink, PlatformOperatorTruthHubLinkAdmin)


class PlatformOperatorPhaseBLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(PlatformOperatorPhaseBLink, PlatformOperatorPhaseBLinkAdmin)


class PlatformOperatorWorkflowSimulatorLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorWorkflowSimulatorLink, PlatformOperatorWorkflowSimulatorLinkAdmin
)


class PlatformOperatorSupportDashboardLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorSupportDashboardLink, PlatformOperatorSupportDashboardLinkAdmin
)


class PlatformOperatorTenantHealthLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorTenantHealthLink, PlatformOperatorTenantHealthLinkAdmin
)


class PlatformOperatorCommandCenterLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorCommandCenterLink, PlatformOperatorCommandCenterLinkAdmin
)


class PlatformOperatorOrchestrationWorkbenchLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorOrchestrationWorkbenchLink,
    PlatformOperatorOrchestrationWorkbenchLinkAdmin,
)


class PlatformOperatorSuperDashboardLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "surface_tier", "category", "sort_order", "updated_at")
    list_filter = ("surface_tier", "category")
    list_editable = ("sort_order", "surface_tier")
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorSuperDashboardLink,
    PlatformOperatorSuperDashboardLinkAdmin,
)


class PlatformOperatorSuperSchoolsListLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorSuperSchoolsListLink,
    PlatformOperatorSuperSchoolsListLinkAdmin,
)


class PlatformOperatorSuperAnalyticsOverviewLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorSuperAnalyticsOverviewLink,
    PlatformOperatorSuperAnalyticsOverviewLinkAdmin,
)


class PlatformOperatorPlatformHubLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorPlatformHubLink,
    PlatformOperatorPlatformHubLinkAdmin,
)


class PlatformOperatorMigrationCloudLinkAdmin(ModelAdmin):
    list_display = ("slug", "label", "category", "sort_order", "updated_at")
    list_editable = ("sort_order",)
    ordering = ("sort_order", "slug")
    search_fields = ("slug", "label", "href", "category")


register_platform_admin(
    PlatformOperatorMigrationCloudLink,
    PlatformOperatorMigrationCloudLinkAdmin,
)


class FleetGovernedChangeAdminForm(forms.ModelForm):
    apply_surface_preset = forms.ChoiceField(
        required=False,
        label=_("Apply surface (preset)"),
        choices=fleet_apply_surface_preset_choices,
        help_text=_(
            "Pick a control-plane target to fill the URL path. "
            "If you type a manual path below, the manual value wins."
        ),
    )

    class Meta:
        model = FleetGovernedChange
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_surface_name_for_payload: str | None = None
        payload = getattr(self.instance, "payload", None) or {}
        if isinstance(payload, dict):
            name = (payload.get("apply_surface_name") or "").strip()
            if name and "apply_surface_preset" in self.fields:
                self.initial.setdefault("apply_surface_preset", name)

    def clean(self):
        cleaned = super().clean()
        self._apply_surface_name_for_payload = None
        preset = (cleaned.get("apply_surface_preset") or "").strip()
        url_manual = (cleaned.get("apply_surface_url") or "").strip()
        if preset and not url_manual:
            resolved = resolve_fleet_apply_surface(preset)
            if not resolved:
                raise forms.ValidationError(
                    {
                        "apply_surface_preset": _(
                            "This URL name does not resolve in the current configuration."
                        ),
                    }
                )
            cleaned["apply_surface_url"] = resolved
            self._apply_surface_name_for_payload = preset
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        p = dict(obj.payload or {})
        if self._apply_surface_name_for_payload:
            p["apply_surface_name"] = self._apply_surface_name_for_payload
        else:
            url_manual = ""
            if hasattr(self, "cleaned_data"):
                url_manual = (self.cleaned_data.get("apply_surface_url") or "").strip()
            if url_manual:
                p.pop("apply_surface_name", None)
            elif self.is_bound and not (self.data.get("apply_surface_preset") or "").strip():
                p.pop("apply_surface_name", None)
        obj.payload = p
        if commit:
            obj.save()
        return obj


class FleetGovernedChangeAdmin(ModelAdmin):
    form = FleetGovernedChangeAdminForm
    list_display = [
        "id",
        "title",
        "change_type",
        "status",
        "created_by",
        "created_at",
        "applied_at",
    ]
    list_filter = ["status", "change_type"]
    search_fields = ["title", "change_type", "notes"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "applied_at",
        "created_by",
    ]
    ordering = ["-created_at"]
    fieldsets = (
        (None, {"fields": ("title", "change_type", "status")}),
        (_("Scope & payload"), {"fields": ("scope", "payload")}),
        (
            _("Apply surface"),
            {
                "fields": ("apply_surface_preset", "apply_surface_url"),
                "description": _(
                    "Preset resolves to a path on save (manager urlconf first). "
                    "Override with a full path if needed."
                ),
            },
        ),
        (_("Notes"), {"fields": ("notes",)}),
        (
            _("People & outcome"),
            {"fields": ("approved_by", "error_message")},
        ),
        (_("Timestamps"), {"fields": ("created_by", "created_at", "updated_at", "applied_at")}),
    )

    def save_model(self, request, obj, form, change):
        if (
            not change
            and request.user.is_authenticated
            and getattr(request.user, "pk", None)
        ):
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


register_platform_admin(FleetGovernedChange, FleetGovernedChangeAdmin)


class PlatformPhaseBDomainSnapshotAdmin(ModelAdmin):
    """
    Bounded-context payload rows (Batches 4–13): edit per-domain JSON here instead of
    treating siteconfig as the only coordination surface. Sync still runs when the platform site settings row saves.
    """

    list_display = [
        "domain",
        "payload_key_count",
        "payload_key_map_size",
        "payload_checksum_short",
        "updated_at",
    ]
    search_fields = ["domain"]
    readonly_fields = [
        "payload_key_count",
        "payload_checksum",
        "payload_key_checksums",
        "updated_at",
    ]
    ordering = ["domain"]

    fieldsets = (
        (None, {"fields": ("domain", "payload")}),
        (
            _("Typed index"),
            {"fields": ("payload_key_count", "payload_checksum", "payload_key_checksums")},
        ),
        (_("Timestamps"), {"fields": ("updated_at",)}),
    )

    @admin.display(description=_("Key FP map"))
    def payload_key_map_size(self, obj):
        m = obj.payload_key_checksums if isinstance(obj.payload_key_checksums, dict) else {}
        n = len(m)
        return n if n else "—"

    @admin.display(description=_("Checksum"))
    def payload_checksum_short(self, obj):
        c = (obj.payload_checksum or "").strip()
        if len(c) <= 14:
            return c or "—"
        return c[:12] + "…"

    def save_model(self, request, obj, form, change):
        obj.refresh_payload_metadata()
        super().save_model(request, obj, form, change)


register_platform_admin(PlatformPhaseBDomainSnapshot, PlatformPhaseBDomainSnapshotAdmin)


class PlatformReportPlatformSkuDefaultAdmin(ModelAdmin):
    """Singleton: operator default report-platform bundle for manifest plan_entitlements."""

    list_display = ["id", "default_bundle_slug", "updated_at"]
    fields = ["default_bundle_slug", "updated_at"]
    readonly_fields = ["updated_at"]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return not PlatformReportPlatformSkuDefault.objects.exists()

    def save_model(self, request, obj, form, change):
        obj.pk = 1
        super().save_model(request, obj, form, change)


register_platform_admin(
    PlatformReportPlatformSkuDefault, PlatformReportPlatformSkuDefaultAdmin
)


class PlatformIntegrationWebhookEventAdmin(ModelAdmin):
    """Append-only audit of inbound integration webhooks (metadata only)."""

    list_display = [
        "received_at",
        "verified",
        "event_type",
        "client_ip",
        "body_sha256_short",
    ]
    list_filter = ["verified"]
    search_fields = ["event_type", "body_sha256", "client_ip"]
    readonly_fields = [
        "received_at",
        "verified",
        "event_type",
        "body_sha256",
        "client_ip",
    ]
    ordering = ["-received_at"]

    @admin.display(description=_("Body sha256"))
    def body_sha256_short(self, obj):
        c = (obj.body_sha256 or "").strip()
        if len(c) <= 16:
            return c or "—"
        return c[:14] + "…"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


register_platform_admin(
    PlatformIntegrationWebhookEvent, PlatformIntegrationWebhookEventAdmin
)


class PlatformEventLogAdmin(ModelAdmin):
    """Append-only platform event log (replay + webhook fan-out source)."""

    list_display = [
        "pk",
        "event_type",
        "tenant_id",
        "school_id",
        "idempotency_key",
        "created_at",
    ]
    list_filter = ["event_type", ("created_at", DateFieldListFilter)]
    search_fields = ["event_type", "tenant_id", "school_id", "idempotency_key", "payload"]
    readonly_fields = ["event_type", "payload", "tenant_id", "school_id", "idempotency_key", "created_at"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    fieldsets = (
        (
            None,
            {"fields": ("event_type", "tenant_id", "school_id", "idempotency_key", "created_at")},
        ),
        (_("Payload"), {"fields": ("payload",)}),
    )

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_staff", False))

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    actions = ["replay_selected_events"]

    @admin.action(description=_("Replay subscribers only (no new webhook deliveries)"))
    def replay_selected_events(self, request, queryset):
        from apps.platform_runtime.event_bus import replay_event

        for obj in queryset[:200]:
            replay_event(obj.pk, dispatch_webhooks=False)


class EventWebhookSubscriptionAdmin(ModelAdmin):
    list_display = [
        "pk",
        "name",
        "target_url",
        "tenant_id",
        "school_id",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "target_url", "tenant_id", "school_id"]
    ordering = ["-created_at"]


class EventWebhookDeliveryAdmin(ModelAdmin):
    list_display = [
        "pk",
        "status",
        "subscription",
        "platform_event",
        "attempt_count",
        "last_http_status",
        "created_at",
        "delivered_at",
    ]
    list_filter = ["status", "subscription"]
    search_fields = [
        "last_error",
        "subscription__name",
        "subscription__tenant_id",
        "platform_event__event_type",
    ]
    readonly_fields = [
        "subscription",
        "platform_event",
        "status",
        "attempt_count",
        "last_http_status",
        "last_error",
        "next_retry_at",
        "delivered_at",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    actions = ["retry_delivery_now"]

    @admin.action(description=_("Deliver now (single attempt / respects DLQ rules)"))
    def retry_delivery_now(self, request, queryset):
        from apps.platform_runtime import event_bus

        for obj in queryset[:100]:
            event_bus.deliver_webhook_attempt(obj.pk)


register_platform_admin(PlatformEventLog, PlatformEventLogAdmin)
register_platform_admin(EventWebhookSubscription, EventWebhookSubscriptionAdmin)
register_platform_admin(EventWebhookDelivery, EventWebhookDeliveryAdmin)


class PilotDefectAdmin(ModelAdmin):
    list_display = (
        "title",
        "status",
        "severity",
        "module",
        "sot_batch",
        "source_school_slug",
        "updated_at",
    )
    list_filter = ("status", "severity", "module")
    search_fields = ("title", "source_school_slug", "linked_test", "sot_batch", "owner")
    ordering = ("-created_at",)


register_platform_admin(PilotDefect, PilotDefectAdmin)


from apps.platform_runtime.models_operator_identity import (
    PlatformOperatorInvite,
    PlatformOperatorProfile,
    PlatformOperatorPromotionRequest,
)


class PlatformOperatorProfileAdmin(ModelAdmin):
    list_display = ("user", "tier", "status", "mfa_required", "updated_at")
    list_filter = ("status", "tier", "mfa_required")
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user", "invited_by")


class PlatformOperatorInviteAdmin(ModelAdmin):
    list_display = ("email", "tier", "expires_at", "accepted_at", "created_at")
    list_filter = ("tier",)
    search_fields = ("email",)
    readonly_fields = ("token", "created_at", "accepted_at")


class PlatformOperatorPromotionRequestAdmin(ModelAdmin):
    list_display = (
        "target_user",
        "requested_tier",
        "status",
        "requester",
        "peer_approver",
        "created_at",
    )
    list_filter = ("status", "requested_tier")
    search_fields = ("target_user__username", "reason")
    raw_id_fields = ("target_user", "requester", "peer_approver")


register_platform_admin(PlatformOperatorProfile, PlatformOperatorProfileAdmin)
register_platform_admin(PlatformOperatorInvite, PlatformOperatorInviteAdmin)
register_platform_admin(
    PlatformOperatorPromotionRequest, PlatformOperatorPromotionRequestAdmin
)

from .models_workflow_10x import (  # noqa: E402
    WorkflowAutopilotApplyLog,
    WorkflowAutopilotPolicy,
    WorkflowDurationStat,
    WorkflowSlaBreach,
)
from .models_workflow_run import WorkflowRun  # noqa: E402


class WorkflowRunAdmin(ModelAdmin):
    list_display = ("workflow_key", "status", "tenant_schema", "started_at", "ended_at")
    list_filter = ("status", "workflow_key")
    search_fields = ("workflow_key", "tenant_schema", "workflow_label")
    readonly_fields = ("started_at", "ended_at", "last_heartbeat_at")


class WorkflowAutopilotPolicyAdmin(ModelAdmin):
    list_display = ("workflow_key", "tenant_schema", "enabled", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("workflow_key", "tenant_schema")


class WorkflowDurationStatAdmin(ModelAdmin):
    list_display = ("workflow_key", "sample_count", "p95_seconds", "updated_at")
    search_fields = ("workflow_key",)


register_platform_admin(WorkflowRun, WorkflowRunAdmin)
register_platform_admin(WorkflowAutopilotPolicy, WorkflowAutopilotPolicyAdmin)
register_platform_admin(WorkflowAutopilotApplyLog, ModelAdmin)
register_platform_admin(WorkflowDurationStat, WorkflowDurationStatAdmin)
register_platform_admin(WorkflowSlaBreach, ModelAdmin)
