"""
Custom admin site configuration.

The platform control plane and tenant admin now run on separate admin site
instances so manager-host routes no longer behave like a tenant surface.
"""

import logging

from apps.dashboard.admin_context import build_admin_dashboard_context

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, path, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.sites import UnfoldAdminSite

# §2.4: Typed tuple for admin context best-effort fallbacks (allowlist 0).
_ADMIN_CONTEXT_FALLBACK_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    OSError,
    NoReverseMatch,
    ImproperlyConfigured,
    TemplateDoesNotExist,
    TemplateSyntaxError,
    DatabaseError,
)


class BaseRunMyCampusAdminSite(UnfoldAdminSite):
    enable_nav_sidebar = True
    login_template = "auth/admin_login.html"
    index_template_name = "admin/index_tenant.html"
    site_header = "Tenant Administration"
    site_title = "Tenant Administration"
    index_title = "Administration Dashboard"

    @staticmethod
    def _host_kind(request) -> str:
        return (getattr(request, "public_host_kind", None) or "").lower()

    @classmethod
    def _is_platform_host(cls, request) -> bool:
        return cls._host_kind(request) in {"manager", "local", ""}

    def is_platform_site(self) -> bool:
        return False

    def each_context(self, request):
        context = super().each_context(request)
        context["is_manager_host"] = self.is_platform_site()
        if self.is_platform_site():
            try:
                from apps.schools.tenant_url import build_public_absolute_url

                context["public_site_url"] = build_public_absolute_url(request, "/")
            except _ADMIN_CONTEXT_FALLBACK_ERRORS:
                context["public_site_url"] = settings.PUBLIC_SITE_URL
        else:
            context["public_site_url"] = None
        try:
            context["extra_userlinks"] = mark_safe(
                render_to_string("admin/extra_user_links.html", context)
            )
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            context["extra_userlinks"] = ""
        try:
            from apps.accounts.mfa_ui_context import build_mfa_ui_context

            context.update(build_mfa_ui_context(request))
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            context["show_mfa_banner"] = False
            context["mfa_setup_url"] = ""
            context["show_mfa_header_icon"] = False
            context["mfa_enrolled"] = False
            context["mfa_setup_needed"] = False
        try:
            context["integrations_changelist_url"] = reverse(
                "admin:integrations_marketplace_integration_changelist"
            )
        except NoReverseMatch:
            context["integrations_changelist_url"] = None
        context["admin_outcome_deck"] = None
        if getattr(request, "user", None) and request.user.is_authenticated:
            try:
                from apps.siteconfig.admin_model_outcomes import (
                    build_admin_outcome_deck_context,
                )

                context["admin_outcome_deck"] = build_admin_outcome_deck_context(
                    request, is_platform_site=self.is_platform_site()
                )
            except _ADMIN_CONTEXT_FALLBACK_ERRORS:
                context["admin_outcome_deck"] = None
        context["admin_steering_hint"] = None
        if self.is_platform_site():
            try:
                from apps.siteconfig.admin_steering import build_admin_steering_hint

                context["admin_steering_hint"] = build_admin_steering_hint(
                    request, is_platform_site=True
                )
            except _ADMIN_CONTEXT_FALLBACK_ERRORS:
                context["admin_steering_hint"] = None
        return context

    def login(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            extra_context["password_reset_url"] = reverse("admin:password_reset")
        except NoReverseMatch:
            try:
                extra_context["password_reset_url"] = reverse(
                    "admin:admin_password_reset"
                )
            except NoReverseMatch:
                extra_context["password_reset_url"] = None
        try:
            from apps.schools.tenant_url import build_public_absolute_url

            extra_context["public_site_url"] = build_public_absolute_url(request, "/")
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            extra_context["public_site_url"] = settings.PUBLIC_SITE_URL
        return super().login(request, extra_context=extra_context)

    def index(self, request, extra_context=None):
        context = build_admin_dashboard_context(
            request,
            base_context=self.each_context(request),
            title=self.index_title,
        )
        if extra_context:
            context.update(extra_context)
        return TemplateResponse(request, self.index_template_name, context)

    def add_view(self, request, *args, **kwargs):
        """After add POST, redirect to request.POST['next'] when safe (return-to-origin)."""
        response = super().add_view(request, *args, **kwargs)
        if (
            request.method == "POST"
            and isinstance(response, HttpResponseRedirect)
            and response.status_code == 302
        ):
            next_url = (request.POST.get("next") or "").strip()
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}
            ):
                return redirect(next_url)
        return response

    def dashboard_redirect(self, request):
        return redirect("admin:index")

    def home_redirect(self, request):
        if self.is_platform_site():
            return redirect("super:dashboard")
        return redirect("/")

    def activity_logs_redirect(self, request):
        if self.is_platform_site():
            try:
                return redirect("platform_incidents_console")
            except NoReverseMatch:
                return redirect("super:command_center")
        return redirect("/compliance/access-logs/")

    def system_health_redirect(self, request):
        return redirect("healthz")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "dashboard/", self.admin_view(self.dashboard_redirect), name="dashboard"
            ),
            path("home/", self.home_redirect, name="home"),
            path("activity-logs/", self.activity_logs_redirect, name="activity_logs"),
            path("system-health/", self.system_health_redirect, name="system_health"),
        ]
        return custom_urls + urls

    def get_app_list(self, request, app_label=None):
        try:
            app_dict = self._build_app_dict(request, app_label)
        except LookupError as e:
            logging.getLogger(__name__).warning(
                "Admin app list skip missing app: %s", e
            )
            app_dict = {}

        # Drop models whose changelist URL could not be resolved (avoids NoReverseMatch in any template using app list)
        for app_name in list(app_dict.keys()):
            app_dict[app_name]["models"] = [
                m for m in app_dict[app_name].get("models", []) if m.get("admin_url")
            ]

        app_order = {
            "accounts": {
                "order": 1,
                "name": "Accounts",
                "icon": "accounts",
                "section": "people",
            },
            "people": {
                "order": 2,
                "name": "People Management",
                "icon": "people",
                "section": "people",
            },
            "auth": {
                "order": 2.1,
                "name": "Auth & Authorization",
                "icon": "auth",
                "section": "people",
            },
            "academics": {
                "order": 4,
                "name": "Academic Structure",
                "icon": "academics",
                "section": "academic",
            },
            "evals": {
                "order": 5,
                "name": "Evaluations & Grading",
                "icon": "evals",
                "section": "academic",
            },
            "reports": {
                "order": 6,
                "name": "Reports & Transcripts",
                "icon": "reports",
                "section": "academic",
            },
            "finance": {
                "order": 7,
                "name": "Finance & Billing",
                "icon": "finance",
                "section": "financial",
            },
            "payroll": {
                "order": 8,
                "name": "Payroll & Leave",
                "icon": "payroll",
                "section": "financial",
            },
            "portal": {
                "order": 9,
                "name": "Portal & Communication",
                "icon": "portal",
                "section": "operations",
            },
            "analytics": {
                "order": 10,
                "name": "Analytics & Insights",
                "icon": "analytics",
                "section": "operations",
            },
            "compliance": {
                "order": 11,
                "name": "Compliance & Audit",
                "icon": "compliance",
                "section": "operations",
            },
            "automation": {
                "order": 12,
                "name": "Automation",
                "icon": "automation",
                "section": "operations",
            },
            "requests": {
                "order": 13,
                "name": "Requests & Approvals",
                "icon": "requests",
                "section": "operations",
            },
            "communication": {
                "order": 14,
                "name": "Communication",
                "icon": "communication",
                "section": "operations",
            },
            "emis": {
                "order": 15,
                "name": "EMIS & Export",
                "icon": "emis",
                "section": "operations",
            },
            "sites": {
                "order": 998,
                "name": "Sites",
                "icon": "sites",
                "section": "system",
            },
            "siteconfig": {
                "order": 1000,
                "name": "Config center",
                "icon": "siteconfig",
                "section": "system",
            },
        }

        app_list = []
        for app_name, app_info in app_dict.items():
            if app_name in app_order:
                cfg = app_order[app_name]
                app_info["app_order"] = cfg["order"]
                app_info["app_label"] = app_name
                app_info["name"] = cfg["name"]
                app_info["section"] = cfg.get("section", "other")
            else:
                app_info["app_order"] = 999
                app_info["app_label"] = app_name
                app_info["section"] = "other"
            app_list.append(app_info)

        model_order = {
            "siteconfig": [
                "SiteSettings",
                "ThemePack",
                "ReportCardStyle",
                "ReportCardStyleAssignment",
                "ReportTemplate",
                "Integration",
                "RegionConfig",
                "GradingScaleConfig",
                "HolidayCalendar",
                "DashboardWidget",
                "DashboardLayout",
                "DashboardUserPreference",
                "UserPreference",
                "FeatureControlAudit",
            ],
        }
        for app_info in app_list:
            order_list = model_order.get(app_info.get("app_label"))
            if not order_list:
                continue
            order_map = {name: idx for idx, name in enumerate(order_list)}
            app_info["models"].sort(
                key=lambda model: (
                    order_map.get(model.get("object_name"), 999),
                    model.get("name", "").lower(),
                )
            )

        app_list = [app_info for app_info in app_list if app_info.get("models")]
        app_list.sort(
            key=lambda app_info: (
                app_info.get("app_order", 999),
                app_info["name"].lower(),
            )
        )

        if self.is_platform_site():
            siteconfig = next(
                (app for app in app_list if app.get("app_label") == "siteconfig"),
                None,
            )
            if siteconfig:
                app_list.remove(siteconfig)
                app_list.insert(0, siteconfig)

        return app_list


class TenantAdminSite(BaseRunMyCampusAdminSite):
    site_header = "Tenant Administration"
    site_title = "Tenant Administration"
    index_title = "Tenant Administration"
    index_template_name = "admin/index_tenant.html"

    def has_permission(self, request):
        return bool(
            not self._is_platform_host(request)
            and request.user.is_active
            and request.user.is_staff
            and request.user.is_superuser
        )


class PlatformAdminSite(BaseRunMyCampusAdminSite):
    """Platform Backoffice: raw CRUD only. Single config surface is Configuration Control Center (siteconfig:console_domains_hub)."""

    site_header = "Platform Backoffice"
    site_title = "Platform Backoffice"
    index_title = "Platform Backoffice"
    index_template_name = "admin/index_superadmin.html"

    def index(self, request, extra_context=None):
        context = build_admin_dashboard_context(
            request,
            base_context=self.each_context(request),
            title=self.index_title,
        )
        app_list = self.get_app_list(request)
        context["app_list"] = app_list
        try:
            from apps.siteconfig.platform_admin_catalog import build_platform_admin_catalog

            context["admin_catalog"] = build_platform_admin_catalog(app_list)
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            logging.getLogger(__name__).warning(
                "platform admin catalog build failed", exc_info=True
            )
            context["admin_catalog"] = {
                "entries": [],
                "sections": [],
                "model_count": 0,
                "app_count": 0,
                "section_count": 0,
            }
        try:
            from apps.siteconfig.admin_steering import build_admin_index_kpi_strip

            context["admin_index_kpis"] = build_admin_index_kpi_strip(context)
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            context["admin_index_kpis"] = []
        try:
            from apps.portal.help_section_nav import admin_catalog_section_nav_items

            context["admin_catalog_section_nav_items"] = admin_catalog_section_nav_items()
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            context["admin_catalog_section_nav_items"] = []
        try:
            from apps.siteconfig.admin_index_surface import (
                build_admin_index_surface_context,
            )

            surface = build_admin_index_surface_context()
            context["admin_index_surface"] = surface
            school_total = surface.get("school_count")
            if school_total is not None:
                school_url = None
                try:
                    school_url = reverse("admin:schools_school_changelist")
                except NoReverseMatch:
                    school_url = None
                school_kpi = {
                    "id": "schools",
                    "label": _("Schools"),
                    "value": school_total,
                }
                if school_url:
                    school_kpi["url"] = school_url
                context["admin_index_kpis"] = [school_kpi] + list(
                    context.get("admin_index_kpis") or []
                )
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            from apps.siteconfig.admin_index_surface import empty_admin_index_surface

            context["admin_index_surface"] = empty_admin_index_surface()
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            logging.getLogger(__name__).warning(
                "admin index surface context failed", exc_info=True
            )
            from apps.siteconfig.admin_index_surface import empty_admin_index_surface

            context["admin_index_surface"] = empty_admin_index_surface()
        if extra_context:
            context.update(extra_context)
        return TemplateResponse(request, self.index_template_name, context)

    def app_index(self, request, app_label, extra_context=None):
        extra_context = dict(extra_context or {})
        try:
            from apps.siteconfig.platform_admin_catalog import enrich_app_index_models

            app_dict = self._build_app_dict(request, app_label)
            app_info = app_dict.get(app_label) or {}
            extra_context["admin_app_index_models"] = enrich_app_index_models(
                app_info
            )
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            logging.getLogger(__name__).warning(
                "platform admin app_index enrich failed", exc_info=True
            )
            extra_context["admin_app_index_models"] = []
        return super().app_index(request, app_label, extra_context=extra_context)

    # AdminOpsShell IA: sections and app order for platform /admin/
    PLATFORM_APP_SECTIONS = (
        "Platform Configuration",
        "Catalog Records",
        "Content & Templates",
        "Integrations & Providers",
        "Marketplace Records",
        "Migration Records",
        "Maintenance & Repair",
        "Access & Permissions",
        "Advanced System Objects",
    )
    PLATFORM_APP_ORDER = {
        "siteconfig": {
            "order": 1,
            "name": "Config center",
            "section": "Platform Configuration",
        },
        "schools": {
            "order": 2,
            "name": "Schools & Tenants",
            "section": "Platform Configuration",
        },
        "registries": {
            "order": 3,
            "name": "Registries",
            "section": "Platform Configuration",
        },
        "policies": {
            "order": 10,
            "name": "Policies & Blueprints",
            "section": "Catalog Records",
        },
        "billing": {"order": 20, "name": "Billing", "section": "Catalog Records"},
        "automation": {
            "order": 40,
            "name": "Automation & Migration",
            "section": "Migration Records",
        },
        "integrations_marketplace": {
            "order": 49,
            "name": "Integrations catalog",
            "section": "Integrations & Providers",
        },
        "marketplace": {
            "order": 50,
            "name": "Marketplace apps",
            "section": "Marketplace Records",
        },
        "observability": {
            "order": 60,
            "name": "Observability",
            "section": "Maintenance & Repair",
        },
        "accounts": {
            "order": 5,
            "name": "Accounts & users",
            "section": "Access & Permissions",
        },
    }

    def is_platform_site(self) -> bool:
        return True

    def has_permission(self, request):
        if not self._is_platform_host(request) or not getattr(request.user, "is_active", False):
            return False
        from apps.schools.control_plane import user_has_control_plane_access
        from apps.platform_runtime.operator_identity import (
            PLATFORM_SCOPE_BREAK_GLASS_ADMIN,
            user_has_platform_scope,
        )

        if not user_has_control_plane_access(request.user):
            return False
        if getattr(request.user, "is_superuser", False):
            return True
        return user_has_platform_scope(
            request.user, PLATFORM_SCOPE_BREAK_GLASS_ADMIN
        )

    def get_app_list(self, request, app_label=None):
        """AdminOpsShell: group and order apps by platform IA (Platform Configuration, Catalog Records, etc.)."""
        try:
            app_dict = self._build_app_dict(request, app_label)
        except LookupError as e:
            # Missing app (e.g. brand_experience not in INSTALLED_APPS on some envs) — skip so admin index still loads
            logging.getLogger(__name__).warning(
                "Admin app list skip missing app: %s", e
            )
            app_dict = {}
        # Drop models whose changelist URL could not be resolved (avoids NoReverseMatch in any template using app list)
        for app_name in list(app_dict.keys()):
            app_dict[app_name]["models"] = [
                m for m in app_dict[app_name].get("models", []) if m.get("admin_url")
            ]
        section_order = {s: i for i, s in enumerate(self.PLATFORM_APP_SECTIONS)}
        # Map app_label to section (one app can only be in one section; use primary section)
        app_list = []
        for app_name, app_info in app_dict.items():
            section = None
            order = 999
            name = app_info.get("name", app_name)
            for key, info in self.PLATFORM_APP_ORDER.items():
                if key == app_name:
                    section = info["section"]
                    order = info["order"]
                    name = info["name"]
                    break
            if not section:
                section = "Advanced System Objects"
            app_info["app_order"] = order
            app_info["app_label"] = app_name
            app_info["name"] = name
            app_info["section"] = section
            app_list.append(app_info)
        app_list = [a for a in app_list if a.get("models")]
        app_list.sort(
            key=lambda a: (
                section_order.get(a.get("section"), 999),
                a.get("app_order", 999),
                a.get("name", "").lower(),
            )
        )
        return app_list


tenant_admin_site = TenantAdminSite(name="admin")
platform_admin_site = PlatformAdminSite(name="admin")
# No shared registry: platform and tenant admin have separate registries.
# Use register_tenant_admin, register_platform_admin, or register_both in app admin.py.

# Backward-compatible registration target used by app admin modules (tenant only).
admin_site = tenant_admin_site


def register_tenant_admin(model, admin_class):
    """Register a model only on tenant admin (tenant host /admin/)."""
    tenant_admin_site.register(model, admin_class)


def register_platform_admin(model, admin_class):
    """Register a model only on platform admin (manager host /admin/)."""
    platform_admin_site.register(model, admin_class)


def register_both(model, admin_class, platform_admin_class=None):
    """Register on both tenant and platform admin. Use platform_admin_class for a different backoffice class."""
    tenant_admin_site.register(model, admin_class)
    platform_admin_site.register(model, platform_admin_class or admin_class)
