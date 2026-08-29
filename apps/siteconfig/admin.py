from django.contrib import admin
from django.conf import settings
from config.admin import register_both, register_platform_admin, register_tenant_admin

from unfold.admin import ModelAdmin
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.contrib import messages
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.db import DatabaseError, models, OperationalError, ProgrammingError
import csv
from datetime import datetime
from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse
from urllib.parse import quote

from apps.brand_experience.models import (
    ThemePack,
)

# Import from concrete submodules so admin loads when siteconfig.models is only partially loaded.
from apps.academics.models import HolidayCalendar, ReportCardStyleAssignment
import apps.siteconfig.models as _siteconfig_models
from .models_platform_catalog import (
    BillingWaiverAuditLog,
    CustomFeatureTicket,
    CustomNuance,
    EducationSystemProfile,
    FeatureFragment,
    PendingNuance,
    RegionConfig,
    RevenueSnapshot,
    TenantAdmissionNumberPolicy,
    WaiverRequest,
)
from .models_tooling import (
    OfficialReportTemplate,
    ReportCardStyle,
    ReportTemplate,
    UserPreference,
)
from .models_global_experience import (
    GradingScaleConfig,
    GlobalSyllabus,
    LearningPassport,
)
from .models_feature_controls import (
    FeatureToggleDefinition,
    FeatureToggleState,
    FeatureUsageEvent,
    GlobalSupportTicket,
    GlobalSupportTicketReply,
    GlobalSupportTicketWebhookEndpoint,
    TourStep,
)
from .models_ai import (
    AIGatewayMetric,
    AIEmbeddingStore,
    AIModelRegistry,
    AIPromptRegistry,
    RegionalAIConfig,
)
from .models_runtime_ops import BreakGlassOverride, BroadcastCampaign
from .models_marketing import BlogPost, MarketingContent, ProductFeedback
from .models_marketing_testimonial import MarketingTestimonial
from .models_dashboard import (
    DashboardUserPreference,
    FeatureControlAudit,
)
from .models_workflow import WorkflowRunLog
from .context_processors import SESSION_KEY
from .theme_palette_groups import THEME_PALETTE_GROUPS, build_theme_pack_groups
from apps.academics.models import AcademicYear
from apps.accounts.models import User
from apps.schools.models import School

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")

# ==========================
# SITE CUSTOMIZER (CORE)
# ==========================
from django import forms
import json


class DashboardLayoutWidget(forms.Textarea):
    """Custom widget to pretty-print JSON for dashboard_layout."""

    def format_value(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                return value
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            return value


class DashboardUserPreferenceForm(forms.ModelForm):
    class Meta:
        model = DashboardUserPreference
        fields = "__all__"
        widgets = {
            "dashboard_layout": DashboardLayoutWidget(
                attrs={"rows": 10, "style": "font-family:monospace; width:90%"}
            ),
            "visible_widgets": forms.SelectMultiple(
                attrs={"size": 8, "style": "width:60%"}
            ),
        }


class TenantSettingsAdminForm(forms.ModelForm):
    """Phase B: only columns that remain on the tenant settings singleton; compliance_profile stored in RuntimeDefaults."""

    compliance_profile = forms.TypedChoiceField(
        required=False,
        choices=(),
        coerce=lambda value: int(value) if value not in ("", None) else None,
        empty_value=None,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Compliance profile",
    )

    class Meta:
        model = _TenantSettingsModel
        fields = [
            f.name
            for f in _TenantSettingsModel._meta.concrete_fields
            if not getattr(f, "primary_key", False) and getattr(f, "editable", True)
        ] + ["compliance_profile"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["compliance_profile"].choices = [("", "---------")]
        current_profile_id = getattr(self.instance, "compliance_profile_id", None)
        try:
            from apps.finance.models import ComplianceProfile

            profiles = list(
                ComplianceProfile.objects.order_by("-is_active", "name").values_list(
                    "pk", "name"
                )
            )
            self.fields["compliance_profile"].choices += [
                (profile_id, name) for profile_id, name in profiles
            ]
        except (ImportError, OperationalError, ProgrammingError):
            if current_profile_id:
                self.fields["compliance_profile"].choices.append(
                    (current_profile_id, f"Profile #{current_profile_id}")
                )
        self.initial["compliance_profile"] = current_profile_id

    def save(self, commit=True):
        instance = super().save(commit=False)
        cp = self.cleaned_data.get("compliance_profile")
        try:
            from apps.finance.models import ComplianceProfile

            if cp:
                prof = ComplianceProfile.objects.filter(pk=cp).first()
                instance.compliance_profile = prof
            else:
                instance.compliance_profile = None
        except (ImportError, OperationalError, ProgrammingError):
            pass
        if commit:
            instance.save()
        return instance


class DashboardUserPreferenceAdmin(ModelAdmin):
    form = DashboardUserPreferenceForm
    change_form_template = "admin/siteconfig/dashboarduserpreference/change_form.html"
    list_display = (
        "user",
        "theme_preference",
        "language",
        "created_at",
        "updated_at",
        "list_widgets",
    )
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    list_filter = ("theme_preference", "language")
    actions = ["set_theme_dark", "set_theme_light"]
    fieldsets = (
        ("User", {"fields": ("user",)}),
        ("Dashboard Layout", {"fields": ("dashboard_layout", "visible_widgets")}),
        ("Theme & Localization", {"fields": ("theme_preference", "language")}),
        ("Accessibility", {"fields": ("high_contrast", "reduced_motion", "font_size")}),
        (
            "Notifications",
            {
                "fields": (
                    "email_notifications",
                    "sms_notifications",
                    "push_notifications",
                )
            },
        ),
        ("UI Preferences", {"fields": ("items_per_page", "sidebar_collapsed")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def list_widgets(self, obj):
        return ", ".join(obj.visible_widgets or [])

    list_widgets.short_description = "Visible Widgets"

    def set_theme_dark(self, request, queryset):
        updated = queryset.update(theme_preference="dark")
        self.message_user(request, f"Set {updated} user(s) to dark mode.")

    set_theme_dark.short_description = "Set theme to Dark"

    def set_theme_light(self, request, queryset):
        updated = queryset.update(theme_preference="light")
        self.message_user(request, f"Set {updated} user(s) to light mode.")

    set_theme_light.short_description = "Set theme to Light"

    class Media:
        css = {"all": ("admin/css/widgets.css",)}


class DashboardWidgetAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/dashboardwidget/change_form.html"
    list_display = (
        "id",
        "name",
        "page",
        "widget_type",
        "required_role",
        "is_active",
        "order",
    )
    search_fields = ("id", "name", "description")
    list_filter = ("page", "widget_type", "required_role", "is_active")
    ordering = ("order",)
    actions = ["activate_widgets", "deactivate_widgets", "assign_to_role"]
    readonly_fields = ("id",)
    fieldsets = (
        (
            "Widget Info",
            {
                "fields": (
                    "id",
                    "name",
                    "description",
                    "widget_type",
                    "page",
                    "template_path",
                )
            },
        ),
        ("Access Control", {"fields": ("required_role", "allowed_roles")}),
        (
            "Display Settings",
            {
                "fields": (
                    "default_width",
                    "default_column",
                    "default_order",
                    "refresh_interval",
                    "chart_type",
                    "allowed_sizes",
                    "default_size",
                    "allowed_variants",
                    "default_variant",
                    "order",
                    "is_active",
                )
            },
        ),
    )

    def activate_widgets(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} widget(s).")

    activate_widgets.short_description = "Activate selected widgets"

    def deactivate_widgets(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} widget(s).")

    deactivate_widgets.short_description = "Deactivate selected widgets"

    def assign_to_role(self, request, queryset):
        # Example: assign all selected widgets to ADMIN role
        updated = queryset.update(required_role="ADMIN")
        self.message_user(request, f"Assigned {updated} widget(s) to ADMIN role.")

    assign_to_role.short_description = "Assign selected widgets to ADMIN role"

    class Media:
        js = ("admin/js/vendor/jquery/jquery.js",)
        css = {"all": ("admin/css/widgets.css",)}


class DashboardLayoutAdmin(ModelAdmin):
    list_display = ("page", "user", "role", "is_default", "updated_at")
    list_filter = ("page", "role", "is_default")
    search_fields = ("user__username", "role")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Scope", {"fields": ("page", "user", "role", "is_default")}),
        ("Layout", {"fields": ("layout",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    formfield_overrides = {
        # Pretty-print JSON for readability
        models.JSONField: {
            "widget": DashboardLayoutWidget(
                attrs={"rows": 12, "style": "font-family:monospace; width:90%"}
            )
        },
    }


# v3.56 — Admin form that overlays the cockpit_payload editor onto the
# existing TenantSettingsAdminForm. The flat cockpit fields are declared
# on CockpitPayloadForm and re-used here so the operator sees the same
# UX in /admin/ as on /siteconfig/super/configure/cockpit/.
from .forms_cockpit import CockpitPayloadForm as _CockpitPayloadForm


class TenantSettingsAdminFormWithCockpit(TenantSettingsAdminForm):
    """Subclass that injects the v3.56 cockpit-payload editor fields.

    The parent form (``TenantSettingsAdminForm``) dynamically pulls every
    concrete field on ``SiteSettings`` — so the JSON column itself is
    already a member. We hide that raw JSON widget, declare the flat
    fields from ``CockpitPayloadForm``, and re-use its parse / serialize
    helpers in ``__init__`` / ``clean()`` so admin saves write the same
    nested dict the operator UI writes.
    """

    # Declare the flat cockpit fields at CLASS level (copied from
    # ``CockpitPayloadForm``) rather than adding them in ``__init__``. Django's
    # admin ``get_form`` builds this form via
    # ``modelform_factory(fields=flatten_fieldsets(...))`` and validates every
    # fieldset field name against the form's *declared* fields at class-creation
    # time — which happens BEFORE ``__init__`` runs. Adding the cockpit fields
    # only in ``__init__`` therefore made the change page 500 with
    # "Unknown field(s) (...) specified for SiteSettings" for every field the
    # "Cockpit configuration" fieldset lists. All cockpit fields are
    # ``required=False``, so declaring them here is validation-safe. In a class
    # body ``locals()`` IS the namespace that becomes the class dict, so this
    # registers them as declared fields exactly as if each were written out by
    # hand (the comprehension's loop vars are scoped to it and do not leak).
    locals().update(
        {
            _cockpit_field_name: _cockpit_field
            for _cockpit_field_name, _cockpit_field in _CockpitPayloadForm.base_fields.items()
            if _cockpit_field_name != "cockpit_payload"
        }
    )
    # Also carry CockpitPayloadForm's class-level DATA attributes — the
    # ``_*_FIELD_TO_KEY`` maps and ``*_FIELDS`` tuples that
    # ``_seed_initial_from_payload`` / ``_build_payload`` read off ``self``.
    # Without these the seeded/round-tripped payload raises ``AttributeError``
    # (e.g. ``_FRONT_OFFICE_FIELD_TO_KEY``) the moment the form is instantiated.
    # Only non-callables are copied (methods/Meta/Media stay on their own class,
    # and this form defines its own ``__init__`` / ``clean``); ``base_fields`` /
    # ``declared_fields`` are excluded so the metaclass-computed field surface of
    # THIS form is not clobbered.
    locals().update(
        {
            _cockpit_attr_name: _cockpit_attr_val
            for _cockpit_attr_name, _cockpit_attr_val in vars(_CockpitPayloadForm).items()
            if not _cockpit_attr_name.startswith("__")
            and not callable(_cockpit_attr_val)
            and _cockpit_attr_name not in {"base_fields", "declared_fields", "media"}
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The flat cockpit fields are declared at class level (above). Here we
        # only hide the raw JSON widget (if the parent form surfaced it) and
        # seed the flat fields' initials from the stored payload so the editor
        # round-trips.
        if "cockpit_payload" in self.fields:
            self.fields["cockpit_payload"].widget = forms.HiddenInput()
            self.fields["cockpit_payload"].required = False
        _CockpitPayloadForm._seed_initial_from_payload(
            self, getattr(self.instance, "cockpit_payload", None) or {}
        )

    # The admin "Cockpit configuration" fieldset edits ONLY these three payload
    # sections; every other cockpit section is configured on the dedicated
    # cockpit page and must survive a SiteSettings save untouched.
    _COCKPIT_ADMIN_SECTIONS = ("footer", "community_band", "newsletter_band")

    def clean(self):
        cleaned = super().clean() or {}
        built = _CockpitPayloadForm._build_payload(self, cleaned)
        # ``_build_payload`` rebuilds ALL cockpit sections from the flat fields,
        # and ``set_cockpit_payload`` replaces the stored payload wholesale — so
        # persisting the full rebuild would wipe the ~37 dashboard cockpit
        # sections whose fields this fieldset does not render (they rebuild
        # empty). Overlay ONLY the three edited sections onto the existing
        # stored payload so a footer/community/newsletter save is non-destructive.
        existing = dict(getattr(self.instance, "cockpit_payload", None) or {})
        for _section in self._COCKPIT_ADMIN_SECTIONS:
            if _section in built:
                existing[_section] = built[_section]
        cleaned["cockpit_payload"] = existing
        # Phase B: cockpit_payload moved off SiteSettings to RuntimeDefaults.payload;
        # the admin persists it in save_model() via set_cockpit_payload(). No
        # model-instance mirror (the column no longer exists).
        return cleaned


class TenantSettingsAdmin(ModelAdmin):
    """
    Main Site Customizer UI.
    Enforces a single settings row and groups options cleanly.
    """

    change_form_template = "admin/siteconfig/sitesettings/change_form.html"
    form = TenantSettingsAdminFormWithCockpit
    # form assigned below after TenantSettingsAdminForm definition

    def get_form(self, request, obj=None, **kwargs):
        """Strip readonly / virtual admin fields from modelform_factory field list."""
        fields = kwargs.get("fields")
        if fields:
            blocked_fields = {
                "theme_color_tools_link_block",
                "platform_global_branding_notice",
                "portal_features_help",
                "automation_overview_block",
                "rbac_discovery_block",
                "integrations_api_center_block",
                "runtime_defaults_notice",
            }
            if self.admin_site.is_platform_site():
                blocked_fields.add("compliance_profile")
            kwargs["fields"] = [f for f in fields if f not in blocked_fields]
        return super().get_form(request, obj=obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if not self.admin_site.is_platform_site():
            return fieldsets
        filtered = []
        for title, options in fieldsets:
            field_names = options.get("fields")
            if not field_names or "compliance_profile" not in field_names:
                filtered.append((title, options))
                continue
            filtered_fields = tuple(
                field for field in field_names if field != "compliance_profile"
            )
            filtered.append((title, {**options, "fields": filtered_fields}))
        return filtered

    # Only allow ONE row
    def has_add_permission(self, request):
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        return self._is_site_admin(request.user) and (
            # config-resolver-allow: singleton row EXISTENCE check gates admin add permission (not a keyed value read)
            get_platform_site_settings_record(create=False) is None
        )

    def has_delete_permission(self, request, obj=None):
        return False

    def _is_site_admin(self, user) -> bool:
        role = (getattr(user, "role", "") or "").upper()
        # Superuser, or a tenant ADMIN / SUPERADMIN. is_staff is intentionally NOT
        # required: this admin is registered only on the tenant_admin_site, whose
        # TenantAdminSite.has_permission already scopes entry to a school-bound
        # admin/owner before any per-model check runs. Self-service tenant owners
        # are role-based SchoolMembership users and are NOT Django is_staff, so an
        # is_staff conjunct here locked them out of their own site settings — the
        # same class of bug as the tenant_admin_required / FINANCE-LOCKOUT fix.
        return bool(
            getattr(user, "is_superuser", False)
            or role in {User.Role.ADMIN, User.Role.SUPERADMIN}
        )

    def has_view_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_module_permission(self, request):
        # Keep the model hidden for non-admin staff; other siteconfig models remain visible via their own admins.
        return self._is_site_admin(request.user)

    readonly_fields = (
        "updated_at",
        "logo_preview",
        "site_summary",
        "platform_global_branding_notice",
        "theme_color_tools_link_block",
        "portal_features_help",
        "automation_overview_block",
        "rbac_discovery_block",
        "integrations_api_center_block",
        "runtime_defaults_notice",
    )

    fieldsets = (
        (
            "At a glance",
            {
                "classes": ("tab",),
                "description": "Current site state.",
                "fields": ("site_summary",),
            },
        ),
        (
            "Platform branding",
            {
                "classes": ("tab",),
                "description": (
                    "Logos, theme packs, and report defaults live on "
                    "<strong>Platform global branding</strong> (Phase B Batch 3)."
                ),
                "fields": (
                    "platform_global_branding_notice",
                    "theme_color_tools_link_block",
                ),
            },
        ),
        (
            "Operations",
            {
                "classes": ("tab",),
                "fields": ("maintenance_mode",),
            },
        ),
        (
            "Compliance pointer",
            {
                "classes": ("tab",),
                "description": "Stores compliance profile id in Runtime defaults payload (Phase B).",
                "fields": ("compliance_profile",),
            },
        ),
        (
            "Where did my settings go?",
            {
                "classes": ("tab",),
                "fields": (
                    "runtime_defaults_notice",
                    "portal_features_help",
                    "integrations_api_center_block",
                    "automation_overview_block",
                ),
            },
        ),
        (
            "Cockpit configuration",
            {
                "classes": ("tab",),
                "description": (
                    "v3.56 cockpit configurability cascade — operator-published "
                    "values for the footer, community band, and newsletter band. "
                    "Empty fields fall through to per-host defaults."
                ),
                "fields": (
                    _CockpitPayloadForm.FOOTER_FIELDS
                    + _CockpitPayloadForm.COMMUNITY_FIELDS
                    + _CockpitPayloadForm.NEWSLETTER_FIELDS
                ),
            },
        ),
        (
            "Metadata",
            {
                "classes": ("tab",),
                "fields": ("updated_at",),
            },
        ),
    )

    # Vertical sidebar navigation for Site Settings (Phase 6.1: logical buckets for non-technical admins).
    SETTINGS_NAV_GROUPS = [
        (
            "Branding & experience",
            [
                ("At a glance", "at-a-glance"),
                ("Platform branding", "platform-branding"),
            ],
        ),
        (
            "System",
            [
                ("Operations", "operations"),
                ("Compliance pointer", "compliance-pointer"),
                ("Cockpit configuration", "cockpit-configuration"),
                ("Where did my settings go?", "where-did-settings-go"),
                ("Metadata", "metadata"),
            ],
        ),
    ]

    # Shared palette groups for Theme & Experience.
    ADMIN_PALETTE_GROUPS = THEME_PALETTE_GROUPS

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        # Ensure title is "Site Settings" (avoid any pluralisation that could produce "Site Settingss")
        extra_context.setdefault("title", "Site Settings")
        all_packs = list(
            ThemePack.objects.filter(applies_to_admin=True, is_active=True).order_by(
                "-is_default", "name"
            )
        )
        admin_theme_packs = [
            p
            for p in all_packs
            if isinstance(getattr(p, "palette", None), dict)
            and (p.palette or {}).get("admin_dashboard")
        ]
        admin_theme_packs_by_group = build_theme_pack_groups(
            admin_theme_packs,
            self.ADMIN_PALETTE_GROUPS,
        )
        extra_context["admin_theme_packs"] = admin_theme_packs
        extra_context["admin_theme_packs_by_group"] = admin_theme_packs_by_group
        extra_context["settings_nav_groups"] = self.SETTINGS_NAV_GROUPS
        # Section slugs present in fieldsets (tab class) for sidebar highlighting
        extra_context["settings_section_slugs"] = [
            slug for _group, items in self.SETTINGS_NAV_GROUPS for _name, slug in items
        ]
        return super().changeform_view(request, object_id, form_url, extra_context)

    def logo_preview(self, obj):
        from apps.platform_runtime.config_resolver import get_effective_config

        logo = get_effective_config(key="logo", request=None, school=None)
        if logo and getattr(logo, "url", None):
            return format_html(
                '<img src="{}" style="height:60px;border-radius:12px;background:#fff;padding:6px;" />',
                logo.url,
            )
        return "No logo uploaded"

    logo_preview.short_description = "Logo Preview"

    def platform_global_branding_notice(self, obj):
        try:
            url = reverse("admin:brand_experience_platformglobalbranding_change", args=[1])
        except NoReverseMatch:
            return mark_safe(
                "<p><strong>Platform global branding</strong> (singleton pk=1) holds "
                "logos, theme packs, and report style defaults.</p>"
            )
        return format_html(
            '<p class="mb-2">{}</p><a class="button" href="{}">{}</a>',
            "Edit the canonical branding row (theme packs, media, report styles).",
            url,
            "Open Platform global branding",
        )

    platform_global_branding_notice.short_description = "Branding storage"

    def site_summary(self, obj):
        """Read-only summary for the first tab: site name, logo, primary color, key toggles."""
        if not obj or not obj.pk:
            return mark_safe("<p>Save once to see the summary.</p>")
        from apps.siteconfig.config_service import get_effective_site_settings

        # config-resolver-allow: namespace with `or obj` fallback fanned into 8+ attribute reads for the summary panel
        eff = get_effective_site_settings(request=None, school=None) or obj
        theme_settings = (
            eff.get_theme_experience_settings()
            if callable(getattr(eff, "get_theme_experience_settings", None))
            else {}
        )
        name = getattr(eff, "site_name", None) or "—"
        primary = (
            str(
                theme_settings.get("primary_color", getattr(eff, "primary_color", ""))
                or ""
            ).strip()
            or "#0d6efd"
        )
        logo_html = ""
        logo = getattr(eff, "logo", None)
        if logo and getattr(logo, "url", None):
            logo_html = format_html(
                '<img src="{}" alt="" style="height:48px;border-radius:8px;background:#fff;padding:4px;margin-right:12px;" />',
                logo.url,
            )
        toggles = []
        for label, val in [
            ("Maintenance", getattr(eff, "maintenance_mode", False)),
            ("Parent portal", getattr(eff, "enable_parent_portal", True)),
            ("Teacher portal", getattr(eff, "enable_teacher_portal", True)),
            ("Student portal", getattr(eff, "enable_student_portal", True)),
            (
                "Reports PDF",
                bool(
                    theme_settings.get(
                        "report_downloads_enabled",
                        getattr(eff, "report_downloads_enabled", True),
                    )
                ),
            ),
            (
                "Dark mode",
                bool(
                    theme_settings.get(
                        "use_dark_mode", getattr(eff, "use_dark_mode", False)
                    )
                ),
            ),
        ]:
            toggles.append(
                '<span style="display:inline-block;margin-right:12px;font-size:0.85rem;">'
                '<span style="color:{};">●</span> {}: {}</span>'.format(
                    "#22c55e" if val else "#94a3b8", label, "On" if val else "Off"
                )
            )
        formatted_inner = (
            '<div><strong>{0}</strong><br><span style="font-size:0.9rem;color:var(--color-base-600,#64748b);">Primary: </span>'
            '<span style="display:inline-block;width:20px;height:20px;border-radius:4px;background:{1};vertical-align:middle;margin-left:4px;"></span>'
            '<code style="font-size:0.8rem;margin-left:4px;">{2}</code></div>'
        ).format(name, primary, primary)
        body = (
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:1rem;padding:0.5rem 0;">'
            + (logo_html if isinstance(logo_html, str) else logo_html)
            + formatted_inner
            + '<div style="flex:1 1 100%;margin-top:0.5rem;border-top:1px solid var(--admin-content-border,rgba(0,0,0,0.08));padding-top:0.5rem;">'
            + "".join(toggles)
            + "</div></div>"
        )
        return mark_safe(body)

    site_summary.short_description = "Summary"

    def theme_color_tools_link_block(self, obj):
        """Launcher to the canonical Theme & Experience page."""
        try:
            url = reverse("studio_os:experience")
        except NoReverseMatch:
            try:
                url = reverse("siteconfig:theme_colors")
            except NoReverseMatch:
                url = "/siteconfig/theme-colors/"
        try:
            next_path = (
                reverse("admin:siteconfig_sitesettings_change", args=[obj.pk])
                + "?stay_theme=1#section-theme-experience"
            )
            sep = "&" if ("?" in url) else "?"
            url = url + sep + "next=" + quote(next_path, safe="/#")
        except NoReverseMatch:
            # Still signal "return to theme section" when admin URL is unavailable (tests / split admin).
            sep = "&" if ("?" in url) else "?"
            url = url + sep + "stay_theme=1"
        return format_html(
            '<p class="mb-2 text-muted">{}</p><a href="{}" class="btn btn-primary">{}</a>',
            "Theme editing is managed on a single page. These settings (Theme pack, Admin theme pack, per-role packs) apply here. Use the button below to open the Theme & Experience studio.",
            url,
            "Open Theme & Experience",
        )

    theme_color_tools_link_block.short_description = ""

    def runtime_defaults_notice(self, obj):
        """Phase B: point operators at RuntimeDefaults JSON + control-plane consoles."""
        try:
            url = reverse("admin:platform_runtime_runtimedefaults_change", args=[1])
        except NoReverseMatch:
            url = ""
        return format_html(
            "<p><strong>Phase B — tenant settings slim row</strong></p>"
            "<p>Most behavioral settings (portal copy, policies, finance automation, "
            "feature flags JSON, etc.) are stored in <code>platform_runtime.RuntimeDefaults.payload</code>. "
            "Edit them via the button below or the Configuration Control Center / Feature Control.</p>"
            "<p><strong>Typed marketplace / integration secrets</strong> (SMS, AI, WhatsApp, SMTP password, "
            "webhook signing, marksheet OCR API key, marketplace partner client secret) live as "
            "<em>first-class columns</em> on the same Runtime defaults admin change page—not inside JSON "
            "exports or Phase B marketplace snapshots. Use <strong>Integrations &amp; API Center</strong> "
            "below for per-integration installs.</p>"
            '<p><a class="button" href="{}">Runtime defaults (payload + typed fields)</a></p>',
            url or "#",
        )

    runtime_defaults_notice.short_description = "Runtime defaults"

    def portal_features_help(self, obj):
        """Link to Feature Control for audited feature toggles."""
        try:
            url = reverse("siteconfig:feature_control_panel")
            return format_html(
                '<p class="mb-3 text-sm">'
                "To toggle features (syllabus, documents, forums, etc.) with an <strong>audit trail</strong>, "
                'use <a href="{}" class="underline">Feature Control</a>.</p>',
                url,
            )
        except NoReverseMatch:
            return ""

    portal_features_help.short_description = ""

    def automation_overview_block(self, obj):
        """Links to Execution Log and Approval Queue in admin (Phase 3.1)."""
        try:
            return render_to_string(
                "admin/siteconfig/sitesettings/automation_overview_block.html",
                context={
                    "execution_log_url": reverse(
                        "admin:automation_automationexecutionlog_changelist"
                    ),
                    "approval_queue_url": reverse(
                        "admin:automation_automationapprovalqueue_changelist"
                    ),
                },
            )
        except (NoReverseMatch, TemplateDoesNotExist):
            return ""

    automation_overview_block.short_description = ""

    def rbac_discovery_block(self, obj):
        """Phase 6.2: Clear entry point for User Permissions / RBAC (who can do what)."""
        try:
            users_url = reverse("admin:accounts_user_changelist")
            groups_url = reverse("admin:auth_group_changelist")
            return format_html(
                '<p class="mb-2 text-sm">Manage users and roles:</p>'
                '<a href="{}" class="btn btn-outline-primary btn-sm me-2">Users</a>'
                '<a href="{}" class="btn btn-outline-primary btn-sm">Groups (roles)</a>',
                users_url,
                groups_url,
            )
        except NoReverseMatch:
            return ""

    rbac_discovery_block.short_description = "User permissions (who can do what)"

    def integrations_api_center_block(self, obj):
        """Clear entry point for Integrations and API Center (one module)."""
        try:
            integrations_url = reverse(
                "admin:integrations_marketplace_integration_changelist"
            )
            api_center_url = reverse("apicenter:dashboard")
            return format_html(
                '<p class="mb-2 text-sm">Integrations & API Center: manage external integrations (email, SMS, payments, portal links) and turn them on/off with required reason and audit log.</p>'
                '<p class="mb-2 text-sm">Add or edit integration config here; enable/disable with audit on the API Center page.</p>'
                '<p class="mb-2 text-sm text-muted">Platform-wide SMS / AI / WhatsApp / SMTP / webhook / OCR API keys and partner client secrets are '
                "<strong>typed columns on Runtime defaults</strong> (see <em>Runtime defaults</em> above)—not bulk JSON. "
                "Tenant code should call <code>get_effective_marketplace_integration_settings</code> from "
                "<code>apps.platform_runtime.helpers</code>, not read ad-hoc tenant settings handles.</p>"
                '<a href="{}" class="btn btn-outline-primary btn-sm me-2">Manage Integrations (Configuration Engine)</a>'
                '<a href="{}" class="btn btn-primary btn-sm">Open API Center</a>',
                integrations_url,
                api_center_url,
            )
        except NoReverseMatch:
            return ""

    integrations_api_center_block.short_description = "Integrations & API Center"

    def backend_flags_summary(self, obj):
        if callable(getattr(obj, "get_backend_feature_flags", None)):
            flags = obj.get_backend_feature_flags()
        else:
            flags = getattr(obj, "backend_feature_flags", {}) or {}
        console = "On" if flags.get("enable_entity_console") else "Off"
        imp = "On" if flags.get("enable_entity_import") else "Off"
        schema = "On" if flags.get("enable_api_schema_ui") else "Off"
        roles_console = ", ".join(flags.get("allowed_roles_entity_console", []))
        roles_import = ", ".join(flags.get("allowed_roles_entity_import", []))
        roles_schema = ", ".join(flags.get("allowed_roles_api_schema", []))
        finance_opt_in = (
            "Required"
            if flags.get("require_guardian_finance_opt_in")
            else "Not required"
        )
        finance_requests = (
            "Enabled"
            if flags.get("allow_finance_access_requests", True)
            else "Disabled"
        )
        return format_html(
            "<ul>"
            "<li>Entity console: {} (roles: {})</li>"
            "<li>Entity import: {} (roles: {})</li>"
            "<li>API schema: {} (roles: {})</li>"
            "<li>Max bulk rows: {}</li>"
            "<li>Allow bulk commit: {}</li>"
            "<li>Guardian finance opt-in: {}</li>"
            "<li>Finance access requests: {}</li>"
            "</ul>",
            console,
            roles_console or "—",
            imp,
            roles_import or "—",
            schema,
            roles_schema or "—",
            flags.get("max_bulk_import_rows", ""),
            "Yes" if flags.get("allow_bulk_commit") else "No",
            finance_opt_in,
            finance_requests,
        )

    backend_flags_summary.short_description = "Backend feature flags"

    def save_model(self, request, obj, form, change):
        # When preview mode is enabled, stash the posted values in session for this user only.
        if form and form.is_valid() and form.cleaned_data.get("preview_mode_enabled"):
            preview_payload = {
                key: form.cleaned_data.get(key)
                for key in form.cleaned_data
                if key
                in [
                    "site_name",
                    "tagline",
                    "primary_color",
                    "accent_color",
                    "success_color",
                    "warning_color",
                    "danger_color",
                ]
            }
            request.session[SESSION_KEY] = preview_payload
            request.session["preview_mode_enabled"] = True
            request.session.modified = True
        else:
            # Clear preview session when disabled
            request.session.pop(SESSION_KEY, None)
            request.session["preview_mode_enabled"] = False
            request.session.modified = True
        super().save_model(request, obj, form, change)
        # Phase B: cockpit_payload moved off SiteSettings to RuntimeDefaults.payload;
        # super().save_model() only writes real columns, so persist the
        # form-computed payload via the accessor.
        if form is not None and "cockpit_payload" in getattr(form, "cleaned_data", {}):
            type(obj).set_cockpit_payload(form.cleaned_data.get("cockpit_payload") or {})
        # Audit trail in admin log
        if change:
            summary = (
                ", ".join(form.changed_data) if form and form.changed_data else "saved"
            )
            self.log_change(request, obj, f"Updated tenant site settings ({summary})")
        else:
            self.log_addition(request, obj, {"added": True})


class UserPreferenceAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/userpreference/change_form.html"
    list_display = (
        "user",
        "dashboard_view",
        "timezone",
        "preferred_language",
        "preferred_region",
        "refresh_rate_minutes",
    )
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


class ReportTemplateAdmin(ModelAdmin):
    list_display = (
        "name",
        "slug",
        "template_family",
        "preferred_format",
        "is_active",
        "updated_at",
    )
    list_filter = ("template_family", "preferred_format", "is_active")
    search_fields = ("name", "slug", "template_family")
    readonly_fields = ("created_at", "updated_at")


class OfficialReportTemplateAdmin(ModelAdmin):
    list_display = (
        "name",
        "region_code",
        "sub_system",
        "school",
        "version",
        "is_active",
    )
    list_filter = ("sub_system", "is_active", "region_code")
    search_fields = ("name", "region_code")
    readonly_fields = ("created_at", "updated_at")


class ReportCardStyleAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/reportcardstyle/change_form.html"
    list_display = ("name", "slug", "is_active", "term_template", "annual_template")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        (
            "Color Picker",
            {
                "description": "Searching for that perfect color? Use our hex color picker to browse millions of colors and harmonies, and export Hex, RGB, HSL and OKLCH codes.",
                "fields": ("primary_color", "accent_color"),
            },
        ),
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "description",
                    "term_template",
                    "annual_template",
                )
            },
        ),
        (
            "Report styling",
            {
                "fields": (
                    "watermark_text",
                    "header_tagline",
                    "css_snippet",
                    "labels",
                    "layout_config",
                )
            },
        ),
        ("Options", {"fields": ("is_active",)}),
    )


class ReportCardStyleAssignmentAdmin(ModelAdmin):
    list_display = ("classroom", "style")
    search_fields = ("classroom__name", "style__name")


# ==========================
# INTEGRATIONS / PLUGINS
# ==========================
class IntegrationAdmin(ModelAdmin):
    """
    Unified integrations: plugin config + API Center governance (one module).
    Examples: Email, SMS, Payments, Analytics. Toggle enabled in API Center with audit.
    """

    list_display = (
        "name",
        "slug",
        "provider",
        "category",
        "enabled",
        "updated_at",
    )

    list_filter = (
        "provider",
        "category",
        "enabled",
    )

    search_fields = (
        "name",
        "slug",
        "provider",
    )

    ordering = ("provider", "name")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("last_call_at", "created_at", "updated_at")
    raw_id_fields = ("school",)


# ==========================
# REGIONAL CONFIGURATION
# ==========================


class GradingScaleConfigInline(admin.TabularInline):
    """
    Inline admin for grading scales within a region.
    Shows all 5 scale types per region with validation and grade breakpoint previews.
    """

    model = GradingScaleConfig
    extra = 0
    fields = (
        "scale_type",
        "min_score",
        "max_score",
        "grade_a_min",
        "grade_b_min",
        "grade_c_min",
        "grade_d_min",
        "grade_f_min",
        "display_format",
        "grade_preview",
    )
    readonly_fields = ("grade_preview",)
    ordering = ("scale_type",)

    def grade_preview(self, obj):
        """Display a visual preview of grade breakpoints."""
        if not obj.pk:
            return "—"

        grades = {
            "A": f"{obj.grade_a_min}+",
            "B": f"{obj.grade_b_min}-{obj.grade_a_min - 0.01}",
            "C": f"{obj.grade_c_min}-{obj.grade_b_min - 0.01}",
            "D": f"{obj.grade_d_min}-{obj.grade_c_min - 0.01}",
            "F": f"< {obj.grade_d_min}",
        }

        html = '<div style="font-size: 12px; line-height: 1.6;">'
        colors = {
            "A": "#28a745",
            "B": "#17a2b8",
            "C": "#ffc107",
            "D": "#fd7e14",
            "F": "#dc3545",
        }
        for grade, range_text in grades.items():
            color = colors.get(grade, "#6c757d")
            html += f'<span style="background: {color}; color: white; padding: 2px 6px; margin: 2px; border-radius: 3px; font-weight: bold;">{grade}: {range_text}</span><br>'
        html += "</div>"

        return mark_safe(html)

    grade_preview.short_description = "Grade Breakpoints"


class EducationSystemProfileInline(admin.TabularInline):
    """
    Inline: Education systems for this region (Part 1 / Part 4 item 6).
    Exposes EducationSystemProfile per RegionConfig in region UI.
    """

    model = EducationSystemProfile
    extra = 0
    fields = (
        "code",
        "name",
        "sub_system",
        "approval_status",
        "is_default",
        "is_active",
        "term_count_per_year",
        "grading_scale",
    )
    readonly_fields = ()
    ordering = ("code",)
    fk_name = "region"
    verbose_name = "Education system (this region)"
    verbose_name_plural = "Education systems for this region"


class HolidayCalendarInline(admin.TabularInline):
    """
    Inline admin for holiday calendars within a region.
    Shows per-academic-year holidays with overlap detection.
    """

    model = HolidayCalendar
    extra = 1
    fields = (
        "academic_year",
        "name",
        "date_start",
        "date_end",
        "holiday_type",
        "is_working_day",
        "description",
        "overlap_status",
    )
    readonly_fields = ("overlap_status",)
    ordering = ("academic_year", "date_start")

    def get_queryset(self, request):
        """Filter to current academic year."""
        qs = super().get_queryset(request)
        current_year = AcademicYear.objects.filter(is_active=True).first()  # tenant-isolation-allow: django-admin-list-filter (staff-only superadmin admin; cross-tenant by intent for the platform's holiday overlap view)
        if current_year:
            return qs.filter(academic_year=current_year)
        return qs

    def overlap_status(self, obj):
        """Show warning if this holiday overlaps with another."""
        if not obj.pk:
            return "—"

        overlapping = HolidayCalendar.objects.filter(
            region=obj.region,
            academic_year=obj.academic_year,
            date_start__lt=obj.date_end,
            date_end__gte=obj.date_start,
        )
        overlapping = overlapping.exclude(pk=obj.pk)

        if overlapping.exists():
            return format_html(
                '<span style="color: #fd7e14; font-weight: bold;">⚠ Overlaps with {}</span>',
                ", ".join([o.name for o in overlapping]),
            )
        return format_html('<span style="color: #28a745;">✓ No overlaps</span>')

    overlap_status.short_description = "Overlap Check"


class RegionConfigAdmin(ModelAdmin):
    """
    Admin interface for regional configurations.
    Manages regions, their settings, grading scales, and holidays.
    """

    list_display = (
        "code_display",
        "name",
        "timezone",
        "grading_scale",
        "default_currency",
        "academic_start",
        "terms_count",
        "scales_status",
    )
    list_filter = ("grading_scale", "default_currency", "academic_year_start_month")
    search_fields = ("code", "name", "timezone")
    readonly_fields = (
        "created_at",
        "updated_at",
        "region_statistics",
        "configuration_summary",
    )

    fieldsets = (
        ("Basic Information", {"fields": ("code", "name", "default_language")}),
        (
            "Regional Settings",
            {
                "fields": (
                    "timezone",
                    "date_format",
                    "grading_scale",
                    "default_currency",
                    "academic_year_start_month",
                    "term_count_per_year",
                )
            },
        ),
        (
            "Portal Features",
            {
                "fields": (
                    "enable_online_admissions",
                    "enable_parent_portal",
                    "enable_student_portal",
                )
            },
        ),
        (
            "Statistics & Summary",
            {
                "fields": ("region_statistics", "configuration_summary"),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    inlines = [
        EducationSystemProfileInline,
        GradingScaleConfigInline,
        HolidayCalendarInline,
    ]

    actions = ["clone_region", "validate_configuration", "export_config"]

    def _is_site_admin(self, user) -> bool:
        role = (getattr(user, "role", "") or "").upper()
        return bool(
            user.is_superuser
            or (user.is_staff and role in {User.Role.ADMIN, User.Role.SUPERADMIN})
        )

    def has_view_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return self._is_site_admin(request.user)

    def has_module_permission(self, request):
        return self._is_site_admin(request.user)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            summary = (
                ", ".join(form.changed_data) if form and form.changed_data else "saved"
            )
            self.log_change(request, obj, f"Updated RegionConfig ({summary})")
        else:
            self.log_addition(request, obj, {"added": True})

    def code_display(self, obj):
        """Display region code with flag emoji."""
        flags = {
            "CMR": "🇨🇲",
            "USA": "🇺🇸",
            "GBR": "🇬🇧",
            "KEN": "🇰🇪",
            "NGA": "🇳🇬",
            "FRA": "🇫🇷",
            "DEU": "🇩🇪",
        }
        flag = flags.get(obj.code, "🌍")
        return format_html("{} <strong>{}</strong>", flag, obj.code)

    code_display.short_description = "Region"

    def academic_start(self, obj):
        """Display academic year start month."""
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        return (
            months[obj.academic_year_start_month - 1]
            if obj.academic_year_start_month
            else "—"
        )

    academic_start.short_description = "Year Starts"

    def terms_count(self, obj):
        """Display number of terms per year."""
        return format_html(
            '<span style="background: #e7f3ff; padding: 3px 8px; border-radius: 3px;">{} terms</span>',
            obj.term_count_per_year,
        )

    terms_count.short_description = "Terms/Year"

    def scales_status(self, obj):
        """Display status of grading scales configuration."""
        count = obj.gradingscaleconfig_set.count()
        if count == 5:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Complete ({}/5)</span>',
                count,
            )
        elif count > 0:
            return format_html(
                '<span style="color: #ffc107; font-weight: bold;">⚠ Partial ({}/5)</span>',
                count,
            )
        return format_html(
            '<span style="color: #dc3545; font-weight: bold;">✗ Incomplete ({}/5)</span>',
            count,
        )

    scales_status.short_description = "Grading Scales"

    def region_statistics(self, obj):
        """Display comprehensive statistics for this region."""
        if not obj.pk:
            return "—"

        scales = obj.gradingscaleconfig_set.count()
        holidays = obj.holidays.count()

        html = f"""
        <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; font-size: 13px;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Grading Scales:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6; text-align: right; font-weight: bold; color: #0066cc;">{scales}/5</td>
                </tr>
                <tr>
                    <td style="padding: 8px;"><strong>Holiday Entries:</strong></td>
                    <td style="padding: 8px; text-align: right; font-weight: bold; color: #0066cc;">{holidays}</td>
                </tr>
            </table>
        </div>
        """
        return mark_safe(html)

    region_statistics.short_description = "Region Statistics"

    def configuration_summary(self, obj):
        """Display summary of region configuration."""
        if not obj.pk:
            return "—"

        portal_features = []
        if obj.enable_online_admissions:
            portal_features.append("✓ Online Admissions")
        if obj.enable_parent_portal:
            portal_features.append("✓ Parent Portal")
        if obj.enable_student_portal:
            portal_features.append("✓ Student Portal")

        if not portal_features:
            portal_features = ["✗ No portals enabled"]

        html = f"""
        <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; font-size: 13px;">
            <strong>Localization:</strong><br>
            Language: {obj.default_language} | Timezone: {obj.timezone}<br>
            Date Format: {obj.date_format} | Currency: {obj.default_currency}<br><br>
            <strong>Academic Calendar:</strong><br>
            Academic Year Starts: Month {obj.academic_year_start_month} | Terms: {obj.term_count_per_year}<br><br>
            <strong>Portal Features:</strong><br>
            {" | ".join(portal_features)}<br>
        </div>
        """
        return mark_safe(html)

    configuration_summary.short_description = "Configuration Summary"

    def clone_region(self, request, queryset):
        """Clone a region configuration with all its settings."""
        if queryset.count() != 1:
            self.message_user(
                request, "Please select exactly one region to clone.", messages.ERROR
            )
            return

        source_region = queryset.first()
        new_code = f"{source_region.code}_COPY"

        try:
            # Clone region
            new_region = RegionConfig.objects.create(
                code=new_code,
                name=f"{source_region.name} (Copy)",
                default_language=source_region.default_language,
                timezone=source_region.timezone,
                date_format=source_region.date_format,
                grading_scale=source_region.grading_scale,
                default_currency=source_region.default_currency,
                academic_year_start_month=source_region.academic_year_start_month,
                term_count_per_year=source_region.term_count_per_year,
                enable_online_admissions=source_region.enable_online_admissions,
                enable_parent_portal=source_region.enable_parent_portal,
                enable_student_portal=source_region.enable_student_portal,
            )

            # Clone grading scales
            for scale in source_region.gradingscaleconfig_set.all():
                GradingScaleConfig.objects.create(
                    region=new_region,
                    scale_type=scale.scale_type,
                    min_score=scale.min_score,
                    max_score=scale.max_score,
                    grade_a_min=scale.grade_a_min,
                    grade_b_min=scale.grade_b_min,
                    grade_c_min=scale.grade_c_min,
                    grade_d_min=scale.grade_d_min,
                    grade_f_min=scale.grade_f_min,
                    display_format=scale.display_format,
                )

            self.message_user(
                request,
                f"✓ Region '{source_region.name}' cloned successfully as '{new_region.name}' "
                f"(Code: {new_code}) with {source_region.gradingscaleconfig_set.count()} grading scales.",
                messages.SUCCESS,
            )
        except (
            DatabaseError,
            OperationalError,
            TypeError,
            ValidationError,
            ValueError,
        ) as e:
            self.message_user(
                request, f"✗ Error cloning region: {str(e)}", messages.ERROR
            )

    clone_region.short_description = "🔄 Clone selected region"

    def validate_configuration(self, request, queryset):
        """Validate regional configuration completeness."""
        issues = []

        for region in queryset:
            # Check grading scales
            if region.gradingscaleconfig_set.count() < 5:
                issues.append(
                    f"❌ {region.name}: Missing grading scales ({region.gradingscaleconfig_set.count()}/5)"
                )

            # Check timezone validity
            import pytz

            try:
                pytz.timezone(region.timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                issues.append(f"❌ {region.name}: Invalid timezone '{region.timezone}'")

            # Check currency
            try:
                from apps.registries.services import is_known_currency_code
            except (AttributeError, ImportError, TypeError, ValueError):

                def is_known_currency_code(code):
                    return bool((code or "").strip())
            if not is_known_currency_code(region.default_currency):
                issues.append(
                    f"⚠️  {region.name}: Unknown currency '{region.default_currency}'"
                )

        if issues:
            message = "Configuration Issues Found:\n\n" + "\n".join(issues)
            self.message_user(request, message, messages.WARNING)
        else:
            self.message_user(
                request,
                "✓ All selected regions have valid configurations.",
                messages.SUCCESS,
            )

    validate_configuration.short_description = "✓ Validate configuration"

    def export_config(self, request, queryset):
        """Export region configurations to CSV."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="regions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(
            [
                "Code",
                "Name",
                "Language",
                "Timezone",
                "Date Format",
                "Grading Scale",
                "Currency",
                "Year Start Month",
                "Terms/Year",
                "Admissions",
                "Parent Portal",
                "Student Portal",
                "Grading Scales Count",
            ]
        )

        for region in queryset:
            writer.writerow(
                [
                    region.code,
                    region.name,
                    region.default_language,
                    region.timezone,
                    region.date_format,
                    region.grading_scale,
                    region.default_currency,
                    region.academic_year_start_month,
                    region.term_count_per_year,
                    "Yes" if region.enable_online_admissions else "No",
                    "Yes" if region.enable_parent_portal else "No",
                    "Yes" if region.enable_student_portal else "No",
                    region.gradingscaleconfig_set.count(),
                ]
            )

        return response

    export_config.short_description = "📥 Export to CSV"


class GradingScaleConfigAdmin(ModelAdmin):
    """
    Standalone admin for grading scale configurations.
    Allows detailed management and comparison of scales across regions.
    """

    list_display = (
        "region",
        "scale_type_display",
        "score_range",
        "grade_breakdown",
        "created_at",
    )
    list_filter = ("region", "scale_type")
    search_fields = ("region__name", "scale_type")
    readonly_fields = ("created_at", "grade_table", "calculation_example")

    fieldsets = (
        ("Scale Definition", {"fields": ("region", "scale_type")}),
        ("Score Range", {"fields": ("min_score", "max_score")}),
        (
            "Grade Breakpoints",
            {
                "fields": (
                    "grade_a_min",
                    "grade_b_min",
                    "grade_c_min",
                    "grade_d_min",
                    "grade_f_min",
                )
            },
        ),
        ("Display Settings", {"fields": ("display_format",)}),
        (
            "Preview & Examples",
            {
                "fields": ("grade_table", "calculation_example"),
                "classes": ("collapse",),
            },
        ),
        ("Metadata", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def scale_type_display(self, obj):
        """Display scale type with icon."""
        icons = {"0-20": "📊", "0-100": "💯", "0-10": "📈", "a-f": "🔤", "gpa": "🎓"}
        icon = icons.get(obj.scale_type, "📋")
        return format_html("{} {}", icon, obj.scale_type)

    scale_type_display.short_description = "Scale Type"

    def score_range(self, obj):
        """Display score range."""
        return f"{obj.min_score} - {obj.max_score}"

    score_range.short_description = "Range"

    def grade_breakdown(self, obj):
        """Display grade breakdown summary."""
        return format_html(
            "A: {}&nbsp;&nbsp;B: {}&nbsp;&nbsp;C: {}&nbsp;&nbsp;D: {}&nbsp;&nbsp;F: <{}",
            obj.grade_a_min,
            obj.grade_b_min,
            obj.grade_c_min,
            obj.grade_d_min,
            obj.grade_f_min,
        )

    grade_breakdown.short_description = "Grade Thresholds"

    def grade_table(self, obj):
        """Display a detailed grade table."""
        if not obj.pk:
            return "—"

        html = """
        <table style="border-collapse: collapse; width: 100%; margin: 10px 0;">
            <tr style="background: #f0f0f0;">
                <th style="border: 1px solid #ddd; padding: 8px; text-align: left; font-weight: bold;">Grade</th>
                <th style="border: 1px solid #ddd; padding: 8px; text-align: center; font-weight: bold;">Range</th>
                <th style="border: 1px solid #ddd; padding: 8px; text-align: center; font-weight: bold;">Color</th>
            </tr>
        """

        grades_data = [
            ("A", f"{obj.grade_a_min} - {obj.max_score}", "#28a745"),
            (
                "B",
                f"{obj.grade_b_min} - {float(obj.grade_a_min) - 0.01:.2f}",
                "#17a2b8",
            ),
            (
                "C",
                f"{obj.grade_c_min} - {float(obj.grade_b_min) - 0.01:.2f}",
                "#ffc107",
            ),
            (
                "D",
                f"{obj.grade_d_min} - {float(obj.grade_c_min) - 0.01:.2f}",
                "#fd7e14",
            ),
            ("F", f"{obj.min_score} - {float(obj.grade_d_min) - 0.01:.2f}", "#dc3545"),
        ]

        for grade, range_text, color in grades_data:
            html += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px; font-weight: bold; text-align: center;">{grade}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{range_text}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">
                    <span style="background: {color}; color: white; padding: 4px 10px; border-radius: 3px; font-weight: bold;">●</span>
                </td>
            </tr>
            """

        html += "</table>"
        return mark_safe(html)

    grade_table.short_description = "Grade Distribution"

    def calculation_example(self, obj):
        """Show example score conversions."""
        if not obj.pk:
            return "—"

        test_scores = [
            (obj.max_score, "Maximum score"),
            ((obj.grade_a_min + obj.max_score) / 2, "High A"),
            (obj.grade_a_min, "Low A / High B"),
            (obj.grade_b_min, "Low B / High C"),
            (obj.grade_c_min, "Low C / High D"),
            (obj.grade_d_min, "Low D / Fail"),
            (obj.min_score, "Minimum score"),
        ]

        html = """
        <table style="border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 12px;">
            <tr style="background: #f0f0f0;">
                <th style="border: 1px solid #ddd; padding: 6px; text-align: center; font-weight: bold;">Score</th>
                <th style="border: 1px solid #ddd; padding: 6px; text-align: center; font-weight: bold;">Grade</th>
                <th style="border: 1px solid #ddd; padding: 6px; text-align: left; font-weight: bold;">Example</th>
            </tr>
        """

        for score, description in test_scores:
            grade_letter = obj.get_letter_grade(score)
            colors = {
                "A": "#28a745",
                "B": "#17a2b8",
                "C": "#ffc107",
                "D": "#fd7e14",
                "F": "#dc3545",
            }
            color = colors.get(grade_letter, "#6c757d")

            html += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 6px; text-align: center; font-weight: bold;">{float(score):.2f}</td>
                <td style="border: 1px solid #ddd; padding: 6px; text-align: center;">
                    <span style="background: {color}; color: white; padding: 2px 6px; border-radius: 3px; font-weight: bold;">{grade_letter}</span>
                </td>
                <td style="border: 1px solid #ddd; padding: 6px;">{description}</td>
            </tr>
            """

        html += "</table>"
        return mark_safe(html)

    calculation_example.short_description = "Example Conversions"


class HolidayCalendarAdmin(ModelAdmin):
    """
    Admin interface for holiday calendars.
    Manages holidays, school closures, and special dates per region per year.
    """

    list_display = (
        "name",
        "region",
        "academic_year",
        "date_range",
        "holiday_type_display",
        "is_working_day_display",
        "days_duration",
    )
    list_filter = ("region", "holiday_type", "academic_year", "is_working_day")
    search_fields = ("name", "region__name", "description")
    readonly_fields = ("created_at", "updated_at", "date_range_visual")

    fieldsets = (
        ("Basic Information", {"fields": ("region", "academic_year", "name")}),
        ("Date Range", {"fields": ("date_start", "date_end", "date_range_visual")}),
        ("Holiday Type", {"fields": ("holiday_type", "is_working_day", "description")}),
        (
            "Metadata",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    actions = ["mark_as_working_day", "mark_as_holiday", "export_holidays"]

    def date_range(self, obj):
        """Display date range."""
        if obj.date_start == obj.date_end:
            return str(obj.date_start)
        return f"{obj.date_start} → {obj.date_end}"

    date_range.short_description = "Period"

    def holiday_type_display(self, obj):
        """Display holiday type with icon."""
        type_icons = {
            "school": "🏫",
            "public": "🇨🇲",
            "religious": "⛪",
            "exam": "📝",
            "special": "🎉",
        }
        icon = type_icons.get(obj.holiday_type, "📅")
        return format_html("{} {}", icon, obj.get_holiday_type_display())

    holiday_type_display.short_description = "Type"

    def is_working_day_display(self, obj):
        """Display if this is a working day."""
        if obj.is_working_day:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Working Day</span>'
            )
        return format_html(
            '<span style="color: #dc3545; font-weight: bold;">✗ Off/Holiday</span>'
        )

    is_working_day_display.short_description = "Status"

    def days_duration(self, obj):
        """Calculate number of days."""
        delta = obj.date_end - obj.date_start
        days = delta.days + 1
        if days == 1:
            return "1 day"
        return f"{days} days"

    days_duration.short_description = "Duration"

    def date_range_visual(self, obj):
        """Display visual date range."""
        if not obj.pk:
            return "—"

        start = obj.date_start.strftime("%A, %B %d, %Y")
        end = obj.date_end.strftime("%A, %B %d, %Y")
        delta = obj.date_end - obj.date_start
        days = delta.days + 1

        html = f"""
        <div style="background: #f8f9fa; padding: 10px; border-radius: 5px; font-size: 13px;">
            <strong>Start:</strong> {start}<br>
            <strong>End:</strong> {end}<br>
            <strong>Duration:</strong> {days} day{"s" if days != 1 else ""}<br>
            <strong>Runs from:</strong> Day {obj.date_start.strftime("%j")} to Day {obj.date_end.strftime("%j")} of the year
        </div>
        """
        return mark_safe(html)

    date_range_visual.short_description = "Date Range Details"

    def mark_as_working_day(self, request, queryset):
        """Mark selected holidays as working days."""
        updated = queryset.update(is_working_day=True)
        self.message_user(
            request, f"✓ Marked {updated} item(s) as working day(s).", messages.SUCCESS
        )

    mark_as_working_day.short_description = "✓ Mark as working day"

    def mark_as_holiday(self, request, queryset):
        """Mark selected items as holidays."""
        updated = queryset.update(is_working_day=False)
        self.message_user(
            request, f"✓ Marked {updated} item(s) as holiday(s).", messages.SUCCESS
        )

    mark_as_holiday.short_description = "✗ Mark as holiday"

    def export_holidays(self, request, queryset):
        """Export holiday calendars to CSV."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="holidays_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(
            [
                "Region",
                "Academic Year",
                "Name",
                "Date Start",
                "Date End",
                "Type",
                "Working Day",
                "Duration (Days)",
                "Description",
            ]
        )

        for holiday in queryset:
            duration = (holiday.date_end - holiday.date_start).days + 1
            writer.writerow(
                [
                    holiday.region.name,
                    str(holiday.academic_year),
                    holiday.name,
                    holiday.date_start,
                    holiday.date_end,
                    holiday.get_holiday_type_display(),
                    "Yes" if holiday.is_working_day else "No",
                    duration,
                    holiday.description or "",
                ]
            )

        return response

    export_holidays.short_description = "📥 Export to CSV"


class WeatherLocationAdmin(ModelAdmin):
    list_display = (
        "region",
        "city",
        "label",
        "latitude",
        "longitude",
        "timezone",
        "is_active",
        "sort_order",
    )
    list_filter = ("region", "is_active")
    search_fields = ("city", "label", "region__name", "region__code")
    ordering = ("region__name", "sort_order", "city")


class EducationSystemProfileAdmin(ModelAdmin):
    list_display = (
        "code",
        "name",
        "version",
        "approval_status",
        "region",
        "lineage_key",
        "sub_system",
        "term_count_per_year",
        "grading_scale",
        "is_default",
        "is_active",
        "approved_at",
    )
    list_filter = ("approval_status", "sub_system", "is_default", "is_active", "region")
    search_fields = ("code", "name", "region__name", "region__code")
    ordering = ("lineage_key", "name", "version")
    readonly_fields = ("created_at", "updated_at", "approved_at", "approved_by")
    actions = [
        "mark_profiles_in_review",
        "approve_profiles",
        "deprecate_profiles",
        "clone_profiles_next_version",
    ]

    def mark_profiles_in_review(self, request, queryset):
        updated = queryset.update(
            approval_status=EducationSystemProfile.ApprovalStatus.IN_REVIEW,
            approved_at=None,
            approved_by=None,
        )
        self.message_user(
            request, f"{updated} profile(s) moved to In Review.", messages.SUCCESS
        )

    mark_profiles_in_review.short_description = "Mark selected profiles as In Review"

    def approve_profiles(self, request, queryset):
        now = timezone.now()
        approver_id = (
            request.user.pk
            if getattr(request, "user", None) and request.user.is_authenticated
            else None
        )
        updated = queryset.update(
            approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
            approved_at=now,
            approved_by_id=approver_id,
        )
        self.message_user(request, f"{updated} profile(s) approved.", messages.SUCCESS)

    approve_profiles.short_description = "Approve selected profiles"

    def deprecate_profiles(self, request, queryset):
        updated = queryset.update(
            approval_status=EducationSystemProfile.ApprovalStatus.DEPRECATED,
            is_active=False,
        )
        self.message_user(
            request,
            f"{updated} profile(s) deprecated and deactivated.",
            messages.WARNING,
        )

    deprecate_profiles.short_description = "Deprecate selected profiles"

    def clone_profiles_next_version(self, request, queryset):
        import re

        created = 0
        for profile in queryset:
            major, minor, patch = 1, 0, 0
            match = re.match(r"^\s*(\d+)\.(\d+)\.(\d+)\s*$", str(profile.version or ""))
            if match:
                major = int(match.group(1))
                minor = int(match.group(2))
                patch = int(match.group(3))
            patch += 1
            next_version = f"{major}.{minor}.{patch}"
            base_code = profile.lineage_key or profile.code
            clone_code = f"{base_code}-v{major}-{minor}-{patch}"[:80]
            suffix = 2
            while EducationSystemProfile.objects.filter(code=clone_code).exists():
                tail = f"-r{suffix}"
                clone_code = f"{(f'{base_code}-v{major}-{minor}-{patch}')[: max(1, 80 - len(tail))]}{tail}"
                suffix += 1
            clone = EducationSystemProfile.objects.create(
                code=clone_code,
                name=profile.name,
                lineage_key=profile.lineage_key or profile.code,
                version=next_version,
                region=profile.region,
                sub_system=profile.sub_system,
                is_default=False,
                is_active=True,
                approval_status=EducationSystemProfile.ApprovalStatus.DRAFT,
                academic_year_start_month=profile.academic_year_start_month,
                term_count_per_year=profile.term_count_per_year,
                term_labels=list(profile.term_labels or []),
                grading_scale=profile.grading_scale,
                default_language=profile.default_language,
                default_currency=profile.default_currency,
                default_timezone=profile.default_timezone,
                subject_seed=list(profile.subject_seed or []),
                config=dict(profile.config or {}),
            )
            created += 1
            self.message_user(
                request,
                f"Cloned {profile.code} -> {clone.code} ({clone.version})",
                messages.INFO,
            )
        if created:
            self.message_user(
                request,
                f"{created} next-version profile clone(s) created as Draft.",
                messages.SUCCESS,
            )

    clone_profiles_next_version.short_description = (
        "Clone selected profiles as next semantic version (Draft)"
    )


class FeatureToggleDefinitionAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/featuretoggledefinition/change_form.html"
    list_display = (
        "key",
        "label",
        "category",
        "scope",
        "owner",
        "source",
        "default_enabled",
        "is_active",
        "updated_at",
    )
    list_filter = ("category", "scope", "default_enabled", "is_active")
    search_fields = ("key", "label", "description", "owner", "source")
    readonly_fields = ("created_at", "updated_at")


class FeatureToggleStateAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/featuretogglestate/change_form.html"
    list_display = ("definition", "school", "is_enabled", "updated_by", "updated_at")
    list_filter = ("is_enabled", "school")
    search_fields = ("definition__key", "definition__label", "school__name")
    readonly_fields = ("created_at", "updated_at")


# Section 22: Tenant admission number policy
class TenantAdmissionNumberPolicyAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/tenantadmissionnumberpolicy/change_form.html"
    list_display = (
        "school",
        "strategy",
        "school_code",
        "seq_width",
        "reset_frequency",
        "is_active",
    )
    list_filter = ("strategy", "reset_frequency", "is_active")
    search_fields = ("school__name", "school_code")
    raw_id_fields = ("school",)


# Register: both = platform backoffice + tenant config; platform = manager only; tenant = tenant only
# Platform operators use super:site_settings_list / super:site_settings_edit only (not platform /admin/).
register_tenant_admin(_TenantSettingsModel, TenantSettingsAdmin)
register_tenant_admin(TenantAdmissionNumberPolicy, TenantAdmissionNumberPolicyAdmin)
register_tenant_admin(UserPreference, UserPreferenceAdmin)
register_both(ReportTemplate, ReportTemplateAdmin)
register_both(OfficialReportTemplate, OfficialReportTemplateAdmin)
register_both(ReportCardStyle, ReportCardStyleAdmin)
register_tenant_admin(ReportCardStyleAssignment, ReportCardStyleAssignmentAdmin)
# FeatureToggleDefinition: platform CRUD is super:feature_toggles_list / feature_toggle_* (not platform /admin/).
register_tenant_admin(FeatureToggleDefinition, FeatureToggleDefinitionAdmin)
register_both(FeatureToggleState, FeatureToggleStateAdmin)


class TourStepAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/tourstep/change_form.html"
    list_display = ("context", "sort_order", "code", "title", "school", "is_active")
    list_filter = ("school", "context", "is_active")
    search_fields = ("code", "title", "context", "selector")
    ordering = ("context", "sort_order", "code")


class FeatureUsageEventAdmin(ModelAdmin):
    list_display = ("feature_code", "school", "user", "created_at")
    list_filter = ("feature_code", "school")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


register_both(TourStep, TourStepAdmin)
register_both(FeatureUsageEvent, FeatureUsageEventAdmin)


class PlanAdmin(ModelAdmin):
    """Phase D: Subscription plan (included_features, max_students, max_staff, billing)."""

    list_display = (
        "name",
        "slug",
        "display_order",
        "billing_model",
        "max_students",
        "max_staff",
        "tenant_visible",
        "requires_quote",
        "is_default",
        "is_active",
        "created_at",
    )
    list_filter = ("billing_model", "tenant_visible", "requires_quote", "is_default", "is_active")
    search_fields = ("name", "slug", "audience", "tenant_summary")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "display_order",
                    "audience",
                    "tenant_summary",
                    "tenant_visible",
                    "requires_quote",
                    "is_default",
                    "is_active",
                )
            },
        ),
        ("Limits", {"fields": ("max_students", "max_staff", "included_features")}),
        (
            "Billing",
            {
                "fields": (
                    "billing_model",
                    "base_price",
                    "price_per_student",
                    "tier_rules",
                    "regional_sku_overrides",
                    "billing_cycle_options",
                    "payment_method_options",
                )
            },
        ),
        ("Tenant packaging", {"fields": ("included_usage", "support_policy", "configuration_schema")}),
        ("Meta", {"fields": ("created_at", "updated_at")}),
    )


class PlanAddonAdmin(ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "billing_unit",
        "price",
        "tenant_visible",
        "is_active",
        "created_at",
    )
    list_filter = ("category", "billing_unit", "tenant_visible", "is_active")
    search_fields = ("code", "name", "description")


class CountryMultiplierAdmin(ModelAdmin):
    list_display = (
        "country_code",
        "name",
        "zone",
        "multiplier",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "zone")
    search_fields = ("country_code", "name")


class RegionalAIConfigAdmin(ModelAdmin):
    list_display = (
        "regional_cluster",
        "ollama_base_url",
        "default_model",
        "preferred_model_id",
        "fallback_model",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("regional_cluster", "default_model", "preferred_model_id")


register_platform_admin(RegionalAIConfig, RegionalAIConfigAdmin)


class AIModelRegistryAdmin(ModelAdmin):
    list_display = (
        "regional_cluster",
        "hardware_tier",
        "model_id",
        "is_active",
        "priority",
        "lora_adapter_path",
        "updated_at",
    )
    list_filter = ("is_active", "regional_cluster")
    search_fields = ("regional_cluster", "model_id", "hardware_tier")


register_platform_admin(AIModelRegistry, AIModelRegistryAdmin)


class AIPromptRegistryAdmin(ModelAdmin):
    list_display = (
        "prompt_key",
        "prompt_class",
        "owner",
        "review_status",
        "is_active",
        "updated_at",
    )
    list_filter = ("prompt_class", "review_status", "is_active")
    search_fields = ("prompt_key", "owner", "purpose")
    readonly_fields = ("created_at", "updated_at")


register_platform_admin(AIPromptRegistry, AIPromptRegistryAdmin)


class AIEmbeddingStoreAdmin(ModelAdmin):
    list_display = ("school_id", "conversation_id", "scope", "text_hash", "created_at")
    list_filter = ("scope", "created_at")
    search_fields = ("conversation_id", "text_hash")
    readonly_fields = (
        "school_id",
        "conversation_id",
        "scope",
        "text_hash",
        "embedding",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return False


register_platform_admin(AIEmbeddingStore, AIEmbeddingStoreAdmin)


class AIGatewayMetricAdmin(ModelAdmin):
    list_display = (
        "date",
        "tenant_id",
        "task_type",
        "tier",
        "cost_class",
        "request_count",
        "average_latency_ms",
        "failure_rate",
        "schema_validation_failures",
        "acceptance_rate",
        "manual_correction_rate",
    )
    list_filter = ("date", "task_type", "tier", "cost_class")
    search_fields = ("tenant_id", "task_type", "tier", "cost_class")
    readonly_fields = (
        "date",
        "tenant_id",
        "task_type",
        "tier",
        "cost_class",
        "request_count",
        "total_latency_ms",
        "failure_count",
        "schema_validation_failures",
        "review_count",
        "accepted_count",
        "manual_correction_count",
    )
    date_hierarchy = "date"

    @admin.display(description="Avg latency (ms)")
    def average_latency_ms(self, obj):
        if not obj.request_count:
            return 0
        return round(obj.total_latency_ms / obj.request_count, 2)

    @admin.display(description="Failure rate")
    def failure_rate(self, obj):
        if not obj.request_count:
            return "0.0%"
        return f"{(obj.failure_count / obj.request_count) * 100:.1f}%"

    @admin.display(description="Acceptance rate")
    def acceptance_rate(self, obj):
        if not obj.review_count:
            return "n/a"
        return f"{(obj.accepted_count / obj.review_count) * 100:.1f}%"

    @admin.display(description="Manual edits")
    def manual_correction_rate(self, obj):
        if not obj.review_count:
            return "n/a"
        return f"{(obj.manual_correction_count / obj.review_count) * 100:.1f}%"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return False


register_platform_admin(AIGatewayMetric, AIGatewayMetricAdmin)


class RevenueSnapshotAdmin(ModelAdmin):
    list_display = (
        "school",
        "snapshot_date",
        "actual_revenue",
        "waived_amount",
        "billing_model",
        "country_code",
        "created_at",
    )
    list_filter = ("snapshot_date", "billing_model", "country_code")
    search_fields = ("school__name",)
    readonly_fields = (
        "school",
        "snapshot_date",
        "actual_revenue",
        "waived_amount",
        "billing_model",
        "country_code",
        "student_count",
        "created_at",
    )
    date_hierarchy = "snapshot_date"


register_platform_admin(RevenueSnapshot, RevenueSnapshotAdmin)


class BillingWaiverAuditLogAdmin(ModelAdmin):
    list_display = (
        "school",
        "changed_by",
        "old_billing_type",
        "new_billing_type",
        "created_at",
    )
    list_filter = ("new_billing_type",)
    search_fields = ("school__name", "new_waiver_note")
    readonly_fields = (
        "school",
        "changed_by",
        "old_billing_type",
        "new_billing_type",
        "old_waiver_note",
        "new_waiver_note",
        "created_at",
    )
    date_hierarchy = "created_at"


register_platform_admin(BillingWaiverAuditLog, BillingWaiverAuditLogAdmin)


class WaiverRequestAdmin(ModelAdmin):
    list_display = (
        "school",
        "status",
        "reason_short",
        "decided_by",
        "decided_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("school__name", "reason")
    readonly_fields = ("school", "proof_file", "reason", "created_at", "updated_at")
    date_hierarchy = "created_at"
    actions = ["approve_waiver_requests", "deny_waiver_requests"]

    def reason_short(self, obj):
        return (
            (obj.reason[:50] + "…")
            if obj.reason and len(obj.reason) > 50
            else (obj.reason or "—")
        )

    reason_short.short_description = "Reason"

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != WaiverRequest.Status.PENDING:
            return list(self.readonly_fields) + [
                "status",
                "decided_by",
                "decided_at",
                "decision_note",
            ]
        return list(self.readonly_fields)

    @admin.action(description="Approve selected waiver requests")
    def approve_waiver_requests(self, request, queryset):
        from django.db import transaction

        pending = queryset.filter(status=WaiverRequest.Status.PENDING).select_related(
            "school"
        )
        count = 0
        for wr in pending:
            try:
                with transaction.atomic():
                    school = wr.school
                    old_bt = getattr(school, "billing_type", "") or ""
                    old_wn = (getattr(school, "waiver_note", None) or "")[:500]
                    waiver_note = (wr.reason or "")[:500]
                    school.billing_type = School.BillingType.COMPLIMENTARY
                    school.waiver_note = waiver_note
                    school.save(update_fields=["billing_type", "waiver_note"])
                    BillingWaiverAuditLog.objects.create(
                        school=school,
                        changed_by=request.user,
                        old_billing_type=old_bt,
                        new_billing_type=School.BillingType.COMPLIMENTARY,
                        old_waiver_note=old_wn,
                        new_waiver_note=waiver_note,
                    )
                    wr.status = WaiverRequest.Status.APPROVED
                    wr.decided_by = request.user
                    wr.decided_at = timezone.now()
                    wr.save(
                        update_fields=[
                            "status",
                            "decided_by",
                            "decided_at",
                            "updated_at",
                        ]
                    )
                    count += 1
            except (DatabaseError, OperationalError, TypeError, ValueError) as e:
                self.message_user(
                    request, f"Failed to approve {wr}: {e}", level=messages.ERROR
                )
        if count:
            self.message_user(
                request, f"Approved {count} waiver request(s).", level=messages.SUCCESS
            )

    @admin.action(description="Deny selected waiver requests")
    def deny_waiver_requests(self, request, queryset):
        pending = queryset.filter(status=WaiverRequest.Status.PENDING)
        now = timezone.now()
        updated = pending.update(
            status=WaiverRequest.Status.DENIED,
            decided_by_id=request.user.pk,
            decided_at=now,
            decision_note="Denied by admin",
            updated_at=now,
        )
        if updated:
            self.message_user(
                request, f"Denied {updated} waiver request(s).", level=messages.SUCCESS
            )


register_platform_admin(WaiverRequest, WaiverRequestAdmin)


# ============================================================================
# Section 7: Nuance Engine — CustomNuance, PendingNuance (human-in-the-loop)
# ============================================================================


class CustomNuanceAdmin(ModelAdmin):
    list_display = (
        "school",
        "hook_point",
        "human_description_short",
        "is_active",
        "updated_at",
    )
    list_filter = ("hook_point", "is_active")
    search_fields = ("school__name", "human_description")
    raw_id_fields = ("school",)

    def human_description_short(self, obj):
        if not obj.human_description:
            return "—"
        return (
            (obj.human_description[:60] + "…")
            if len(obj.human_description) > 60
            else obj.human_description
        )

    human_description_short.short_description = "Description"

    def save_model(self, request, obj, form, change):
        from .nuance_engine import nuance_engine_enabled

        if not nuance_engine_enabled(obj.school):
            messages.warning(
                request,
                "Nuance Engine is not enabled for this school (plan/addon). Rule saved but may not run until enabled.",
            )
        super().save_model(request, obj, form, change)


register_platform_admin(CustomNuance, CustomNuanceAdmin)


class PendingNuanceAdmin(ModelAdmin):
    list_display = (
        "school",
        "hook_point",
        "human_explanation_short",
        "status",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )
    list_filter = ("status", "hook_point")
    search_fields = ("school__name", "human_explanation")
    raw_id_fields = ("school", "reviewed_by")
    readonly_fields = ("created_at", "updated_at")
    actions = ["approve_pending_nuances"]

    def human_explanation_short(self, obj):
        if not obj.human_explanation:
            return "—"
        return (
            (obj.human_explanation[:50] + "…")
            if len(obj.human_explanation) > 50
            else obj.human_explanation
        )

    human_explanation_short.short_description = "Explanation"

    @admin.action(description="Approve selected pending nuances")
    def approve_pending_nuances(self, request, queryset):
        from django.db import transaction
        from .nuance_engine import default_test_contexts_for_hook, verify_nuance_safety
        from .models import CustomNuance

        pending = queryset.filter(status=PendingNuance.Status.PENDING).select_related(
            "school"
        )
        count = 0
        errors = []
        for pn in pending:
            test_contexts = default_test_contexts_for_hook(pn.hook_point)
            ok, msg = verify_nuance_safety(
                pn.proposed_logic, test_contexts, reject_negative_fee=True
            )
            if not ok:
                errors.append(f"{pn.school.name} / {pn.hook_point}: {msg}")
                continue
            try:
                with transaction.atomic():
                    CustomNuance.objects.update_or_create(
                        school=pn.school,
                        hook_point=pn.hook_point,
                        defaults={
                            "logic_data": pn.proposed_logic,
                            "human_description": pn.human_explanation or "",
                            "is_active": True,
                        },
                    )
                    pn.status = PendingNuance.Status.APPROVED
                    pn.reviewed_by = request.user
                    pn.reviewed_at = timezone.now()
                    pn.save(
                        update_fields=[
                            "status",
                            "reviewed_by",
                            "reviewed_at",
                            "updated_at",
                        ]
                    )
                    count += 1
            except (DatabaseError, OperationalError, TypeError, ValueError) as e:
                errors.append(f"{pn.school.name} / {pn.hook_point}: {e}")
        if count:
            self.message_user(
                request, f"Approved {count} pending nuance(s).", level=messages.SUCCESS
            )
        for err in errors:
            self.message_user(request, err, level=messages.ERROR)


register_platform_admin(PendingNuance, PendingNuanceAdmin)


class CustomFeatureTicketAdmin(ModelAdmin):
    list_display = ("school", "title", "status", "upvote_count", "is_vip", "created_at")
    list_filter = ("status", "is_vip")
    search_fields = ("title", "description")
    raw_id_fields = ("school", "created_by")


class FeatureFragmentAdmin(ModelAdmin):
    list_display = ("school", "target_hook", "name", "is_active", "schema_version")
    list_filter = ("is_active", "target_hook")
    search_fields = ("name", "target_hook")
    raw_id_fields = ("school", "ticket")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "target_hook" and formfield is not None:
            from .hooks import get_hook_choices

            formfield.choices = get_hook_choices()
        return formfield


register_platform_admin(CustomFeatureTicket, CustomFeatureTicketAdmin)
register_platform_admin(FeatureFragment, FeatureFragmentAdmin)


# Register dashboard preference and widget models for admin configurability
register_tenant_admin(DashboardUserPreference, DashboardUserPreferenceAdmin)


class SuperAdminDashboardPreferenceAdmin(ModelAdmin):
    list_display = ("user", "section_order", "updated_at")
    search_fields = ("user__username",)
    raw_id_fields = ("user",)


register_both(WorkflowRunLog, admin.ModelAdmin)


class FeatureControlAuditAdmin(ModelAdmin):
    list_display = ("created_at", "user", "action", "changes_summary")
    list_filter = ("action",)
    readonly_fields = ("user", "action", "changes", "created_at")
    date_hierarchy = "created_at"

    def changes_summary(self, obj):
        if not obj.changes:
            return "—"
        parts = [
            f"{k}: {v.get('from', '?')}→{v.get('to', '?')}"
            for k, v in list(obj.changes.items())[:3]
        ]
        return ", ".join(parts) + ("…" if len(obj.changes) > 3 else "")

    changes_summary.short_description = "Changes"


register_platform_admin(FeatureControlAudit, FeatureControlAuditAdmin)


# Section 8: Industry Interoperability — ServiceIntegration, WebhookSubscription
class ServiceIntegrationAdmin(ModelAdmin):
    list_display = ("school", "service_name", "service_type", "is_active", "updated_at")
    list_filter = ("service_type", "is_active")
    raw_id_fields = ("school",)
    search_fields = ("service_name",)
    ordering = ("school", "service_name")


# Section 15.2 legacy DynamicField* (siteconfig_dynamicfield*): removed Batch 14 Phase 5b — use metadata app.

# World Engine: GlobalSyllabus, LearningPassport, BreakGlassOverride, BroadcastCampaign
class GlobalSyllabusAdmin(ModelAdmin):
    list_display = ("code", "name", "country_code", "sort_order", "created_at")
    list_filter = ("country_code",)
    search_fields = ("code", "name", "description", "country_code")


class LearningPassportAdmin(ModelAdmin):
    list_display = ("user", "school", "country_code", "external_id", "updated_at")
    list_filter = ("country_code",)
    search_fields = ("user__email", "external_id", "country_code")
    raw_id_fields = ("user", "school")


class BreakGlassOverrideAdmin(ModelAdmin):
    list_display = ("scope", "target_id", "actor", "reason", "created_at")
    list_filter = ("scope",)
    search_fields = ("reason", "target_id")
    raw_id_fields = ("actor",)
    readonly_fields = ("created_at",)


class BroadcastCampaignAdmin(ModelAdmin):
    list_display = (
        "subject",
        "school",
        "status",
        "slide_confirm_required",
        "target_count",
        "created_at",
    )
    list_filter = ("status", "slide_confirm_required")
    search_fields = ("subject", "body")
    raw_id_fields = ("school", "created_by")
    readonly_fields = ("created_at",)


register_both(GlobalSyllabus, GlobalSyllabusAdmin)
register_both(LearningPassport, LearningPassportAdmin)
register_platform_admin(BreakGlassOverride, BreakGlassOverrideAdmin)
register_platform_admin(BroadcastCampaign, BroadcastCampaignAdmin)


class ProductFeedbackAdmin(ModelAdmin):
    list_display = ("title", "region", "module", "status", "upvotes", "created_at")
    list_filter = ("status", "region", "module")
    search_fields = ("title", "description")
    readonly_fields = ("created_at", "updated_at")
    ordering = ["-upvotes", "-created_at"]


register_platform_admin(ProductFeedback, ProductFeedbackAdmin)


class MarketingContentAdmin(ModelAdmin):
    list_display = ("key", "locale", "content_type", "updated_at")
    list_filter = ("locale", "content_type")
    search_fields = ("key", "content_html")
    readonly_fields = ("updated_at",)


register_platform_admin(MarketingContent, MarketingContentAdmin)


class BlogPostAdmin(ModelAdmin):
    list_display = ("title", "slug", "is_published", "published_at", "created_at")
    list_filter = ("is_published",)
    search_fields = ("title", "excerpt", "body_html")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "published_at"


register_platform_admin(BlogPost, BlogPostAdmin)


class MarketingTestimonialAdmin(ModelAdmin):
    list_display = (
        "attribution_name",
        "organization_name",
        "source",
        "rating",
        "is_approved",
        "page_slugs",
        "locale",
        "display_order",
    )
    list_filter = ("source", "is_approved", "locale", "is_active")
    search_fields = ("quote", "attribution_name", "organization_name")
    list_editable = ("is_approved", "display_order")
    readonly_fields = ("approved_at", "approved_by", "created_at", "updated_at")
    ordering = ["display_order", "-created_at"]
    actions = ["approve_selected"]

    @admin.action(description="Approve selected testimonials")
    def approve_selected(self, request, queryset):
        updated = queryset.update(
            is_approved=True,
            approved_at=timezone.now(),
            approved_by=request.user,
        )
        self.message_user(
            request,
            f"Approved {updated} testimonial(s).",
            messages.SUCCESS,
        )


register_platform_admin(MarketingTestimonial, MarketingTestimonialAdmin)


class GlobalSupportTicketReplyInline(admin.TabularInline):
    model = GlobalSupportTicketReply
    extra = 0
    raw_id_fields = ("author",)
    readonly_fields = ("created_at",)


class GlobalSupportTicketAdmin(ModelAdmin):
    list_display = (
        "subject",
        "school",
        "status",
        "priority",
        "user",
        "assigned_to",
        "created_at",
    )
    list_filter = ("status", "priority")
    search_fields = ("subject", "body", "school__name", "user__email")
    raw_id_fields = ("school", "user", "assigned_to")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [GlobalSupportTicketReplyInline]


class GlobalSupportTicketReplyAdmin(ModelAdmin):
    list_display = ("ticket", "visibility", "author", "created_at")
    list_filter = ("visibility",)
    search_fields = ("body", "ticket__subject")
    raw_id_fields = ("ticket", "author")
    readonly_fields = ("created_at",)


class GlobalSupportTicketWebhookEndpointAdmin(ModelAdmin):
    list_display = ("name", "url", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "url")


register_platform_admin(GlobalSupportTicket, GlobalSupportTicketAdmin)
register_platform_admin(GlobalSupportTicketReply, GlobalSupportTicketReplyAdmin)
register_platform_admin(
    GlobalSupportTicketWebhookEndpoint, GlobalSupportTicketWebhookEndpointAdmin
)


# ============================================================================
# Phase G: Sync Center – conflict queue for offline delta-sync
# ============================================================================


# Phase G: SyncConflict model and admin (uncomment when SyncConflict exists in siteconfig.models)
# def _resolve_sync_conflict(conflict, resolution, resolved_by): ...
# class SyncConflictAdmin(ModelAdmin): ...
# admin_site.register(SyncConflict, SyncConflictAdmin)
try:
    from .models import SyncConflict

    #: Admin Status -> the resolution token ``conflict_actions`` speaks.
    _ADMIN_RESOLUTION_TOKENS = {
        SyncConflict.Status.RESOLVED_SERVER: "server",
        SyncConflict.Status.RESOLVED_CLIENT: "client",
        SyncConflict.Status.DISCARDED: "discard",
    }

    def _resolve_sync_conflict(conflict, resolution, resolved_by):
        """Settle one conflict from the admin, through the SAME path as the Sync Center.

        THIS WAS A SECOND IMPLEMENTATION, and it had drifted into the weaker one. Its
        own comment said it mirrored views_sync_center, which has since moved to
        ``conflict_actions`` and grown two guards this copy never got:

          * ``may_resolve`` -- a conflict on a cloud-authoritative record (money,
            grades, identity) may only be settled in the client's favour by
            someone who could have made that write directly. This copy asked nobody,
            so the admin's own Keep-client action wrote a box's refused value
            straight into the cloud record: the bypass that guard exists to close,
            reachable by any staff user with change permission on SyncConflict alone.
          * the down-only field strip -- salary, payroll and leave authorization,
            offboarding and the grading coefficient ride DOWN only. The inbound rail
            removes them from a box push; this copy wrote them.

        Delegating is the fix rather than copying the guards across, because two
        implementations of one rule is what produced the drift in the first place.
        """
        from apps.sync_engine.conflict_actions import apply_resolution

        token = _ADMIN_RESOLUTION_TOKENS.get(resolution)
        if token is None:
            return False, "invalid_resolution"
        return apply_resolution(conflict, token, resolved_by)

    class SyncConflictAdmin(ModelAdmin):
        list_display = (
            "id",
            "school",
            "entity_type",
            "entity_id",
            "status",
            "origin",
            "reported_by",
            "created_at",
        )
        list_filter = ("school", "status", "entity_type", "origin")
        search_fields = ("entity_type", "entity_id", "resolution_note")
        readonly_fields = (
            "school",
            "entity_type",
            "entity_id",
            "client_data",
            "server_data",
            "conflict_fields",
            "origin",
            "client_updated_at",
            "server_updated_at",
            "reported_by",
            "created_at",
        )
        date_hierarchy = "created_at"
        list_per_page = settings.DEFAULT_PAGE_SIZE
        actions = ["resolve_keep_server", "resolve_keep_client", "resolve_discard"]

        def has_add_permission(self, request):
            return False

        def get_queryset(self, request):
            qs = super().get_queryset(request)
            school = getattr(request, "school", None)
            if school and not request.user.is_superuser:
                return qs.filter(school_id=school.id)
            return qs

        def _settle(self, request, queryset, status, label):
            """Run one bulk action and SAY what happened to every row.

            Counted as it goes, not re-queried afterwards. The previous messages ran
            the PENDING filter again AFTER the loop -- by then the rows they meant to
            count had been resolved and were no longer PENDING, so a bulk action that
            worked perfectly reported "Resolved 0 conflict(s)".

            A refusal is surfaced rather than swallowed: with authority now enforced
            here, some rows legitimately will not settle, and an action that silently
            skips them looks identical to one that worked.
            """
            done, refused = 0, []
            for obj in list(queryset.filter(status=SyncConflict.Status.PENDING)):
                ok, reason = _resolve_sync_conflict(obj, status, request.user)
                if ok:
                    done += 1
                else:
                    refused.append("#%s: %s" % (obj.pk, reason))
            self.message_user(
                request, "Resolved %d conflict(s) (%s)." % (done, label)
            )
            if refused:
                self.message_user(
                    request,
                    "Left unresolved: " + "; ".join(refused[:10]),
                    level=messages.WARNING,
                )

        @admin.action(description="Keep server version")
        def resolve_keep_server(self, request, queryset):
            self._settle(
                request, queryset, SyncConflict.Status.RESOLVED_SERVER, "server"
            )

        @admin.action(description="Keep client version")
        def resolve_keep_client(self, request, queryset):
            self._settle(
                request, queryset, SyncConflict.Status.RESOLVED_CLIENT, "client"
            )

        @admin.action(description="Discard")
        def resolve_discard(self, request, queryset):
            self._settle(
                request, queryset, SyncConflict.Status.DISCARDED, "discard"
            )

    register_platform_admin(SyncConflict, SyncConflictAdmin)
except ImportError:
    pass


# v3.59.2 — PlatformPulseSnapshot operator surface.
# Read-only history view of the daily cockpit-pulse capture rows. Operators
# use this to spot beat misses (gaps in the daily cadence) and verify the
# raw values that produce the "+N this week" delta strings on the dashboard.
try:
    from .models_pulse_snapshot import PlatformPulseSnapshot

    class PlatformPulseSnapshotAdmin(ModelAdmin):
        list_display = ("snapshot_date", "metric_key", "raw_value", "display_value", "captured_at")
        list_filter = ("metric_key", "snapshot_date")
        search_fields = ("metric_key", "display_value")
        ordering = ("-snapshot_date", "metric_key")
        date_hierarchy = "snapshot_date"
        readonly_fields = ("snapshot_date", "metric_key", "raw_value", "display_value", "captured_at")
        list_per_page = 50

        def has_add_permission(self, request):
            # Append-only via mgmt command + daily beat; the admin is read-only.
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            # Allow staff to prune old rows manually if retention ever matters.
            return request.user.is_superuser

    register_platform_admin(PlatformPulseSnapshot, PlatformPulseSnapshotAdmin)
except ImportError:
    pass
