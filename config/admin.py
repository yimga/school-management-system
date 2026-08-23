"""
Custom admin site configuration.

The platform control plane and tenant admin now run on separate admin site
instances so manager-host routes no longer behave like a tenant surface.
"""

import functools
import logging

from django.contrib.admin.sites import AlreadyRegistered

from apps.dashboard.admin_context import build_admin_dashboard_context

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, path, reverse, set_urlconf
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
    site_header = "School configuration"
    site_title = "School configuration"
    index_title = "Configuration & records"

    @staticmethod
    def _host_kind(request) -> str:
        return (getattr(request, "public_host_kind", None) or "").lower()

    @classmethod
    def _is_platform_host(cls, request) -> bool:
        host_kind = cls._host_kind(request)
        # The manager (operator / control-plane) host is ALWAYS a platform host — even if a
        # school somehow got resolved onto the request. This is a hard operator<->tenant
        # isolation boundary: the tenant admin site must never open on the manager host, so a
        # resolved school can never downgrade a manager request to "tenant" here.
        if host_kind == "manager":
            return True
        # Otherwise a resolved school marks this as a tenant request (host_kind ambiguous/empty),
        # so the tenant admin site is allowed and the platform admin site refuses.
        if getattr(request, "school", None) is not None:
            return False
        return host_kind in {"local", ""}

    def is_platform_site(self) -> bool:
        return False

    def each_context(self, request):
        context = super().each_context(request)
        context["is_manager_host"] = self.is_platform_site()
        try:
            from apps.siteconfig.admin_navigation_preferences import (
                build_admin_navigation_contract,
            )

            context["admin_navigation_contract"] = build_admin_navigation_contract(
                request, self
            )
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            logging.getLogger(__name__).warning(
                "admin navigation preference fallback", exc_info=True
            )
            context["admin_navigation_contract"] = {
                "version": 1,
                "scope": "unavailable",
                "endpoint": "",
                "preferences": {},
                "limits": {"pinned": 8, "recent": 10},
            }
        try:
            context["admin_field_preferences_url"] = reverse(
                f"{self.name}:field_preferences",
                urlconf=getattr(request, "urlconf", None),
            )
        except NoReverseMatch:
            context["admin_field_preferences_url"] = ""
        try:
            from apps.siteconfig.admin_surface_intelligence import build_admin_surface_profile
            context["admin_surface_profile"] = build_admin_surface_profile(
                user=getattr(request, "user", None), is_platform=self.is_platform_site()
            )
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            logging.getLogger(__name__).warning("admin surface profile fallback", exc_info=True)
            context["admin_surface_profile"] = {
                "role_slug": "operator" if self.is_platform_site() else "admin",
                "tone": "indigo" if self.is_platform_site() else "azure",
            }
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
        context["app_list"] = self.get_app_list(request)
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
        from apps.siteconfig.admin_form_intelligence import (
            admin_field_preferences_view,
        )
        from apps.siteconfig.admin_navigation_preferences import (
            admin_navigation_preferences_view,
        )

        urls = super().get_urls()
        custom_urls = [
            path(
                "navigation-preferences/",
                self.admin_view(
                    lambda request: admin_navigation_preferences_view(
                        request, admin_site=self
                    )
                ),
                name="navigation_preferences",
            ),
            path(
                "field-preferences/",
                self.admin_view(
                    lambda request: admin_field_preferences_view(
                        request, admin_site=self
                    )
                ),
                name="field_preferences",
            ),
            path(
                "dashboard/", self.admin_view(self.dashboard_redirect), name="dashboard"
            ),
            path("home/", self.home_redirect, name="home"),
            path("activity-logs/", self.activity_logs_redirect, name="activity_logs"),
            path("system-health/", self.system_health_redirect, name="system_health"),
        ]
        return custom_urls + urls

    def register(self, model_or_iterable, admin_class=None, **options):
        """Give every operator and tenant registration one form policy owner."""
        from django.contrib.admin import ModelAdmin as _DjangoModelAdmin
        from apps.siteconfig.admin_form_intelligence import (
            AdminFormAutomationMixin,
            AdminInlineAutomationMixin,
        )

        base_class = admin_class or _DjangoModelAdmin
        if not getattr(base_class, "_rmc_admin_form_automation", False):
            base_class = type(
                base_class.__name__,
                (AdminFormAutomationMixin, base_class),
                {"__module__": getattr(base_class, "__module__", __name__)},
            )
        # Inlines are declared as a class attribute rather than registered, so the
        # same injection has to reach them here or they are covered by nothing.
        declared_inlines = list(getattr(base_class, "inlines", ()) or ())
        if declared_inlines:
            wrapped = []
            for inline in declared_inlines:
                if isinstance(inline, type) and not getattr(
                    inline, "_rmc_admin_inline_automation", False
                ):
                    inline = type(
                        inline.__name__,
                        (AdminInlineAutomationMixin, inline),
                        {"__module__": getattr(inline, "__module__", __name__)},
                    )
                wrapped.append(inline)
            base_class = type(
                base_class.__name__,
                (base_class,),
                {
                    "inlines": wrapped,
                    "__module__": getattr(base_class, "__module__", __name__),
                },
            )
        return super().register(model_or_iterable, base_class, **options)

    def get_app_list(self, request, app_label=None):
        request_urlconf = getattr(request, "urlconf", None)
        if request_urlconf:
            set_urlconf(request_urlconf)
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


def tenant_admin_user_has_access(request) -> bool:
    """Shared gate for tenant_admin_site entry and tenant-scoped ModelAdmin permissions.

    Mirrors TenantAdminSite.has_permission so Integration (and other tenant-only)
    ModelAdmins can grant school owners the same access the site gate already allows.
    """
    user = getattr(request, "user", None)
    if not (
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    ):
        return False
    school = getattr(request, "school", None)
    if school is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        from apps.accounts.auth_backends_role_perms import ADMIN_LIKE_ROLES
        from apps.schools.models import SchoolMembership

        membership = (
            SchoolMembership.objects.filter(
                school=school,
                user_id=getattr(user, "pk", None),
                suspended_at__isnull=True,
            )
            .only("role", "is_school_owner")
            .first()
        )
        if membership is None:
            return False
        if getattr(membership, "is_school_owner", False):
            return True
        role_codes = {
            (getattr(membership, "role", "") or "").upper(),
            (getattr(user, "role", "") or "").upper(),
        }
        if role_codes & ADMIN_LIKE_ROLES:
            return True
        return bool(
            hasattr(user, "has_feature_permission")
            and user.has_feature_permission("settings.manage", school=school)
        )
    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
        return False


class _TenantScopedQuerysetMixin:
    """Confine a ModelAdmin's changelist to the request's school (+ global rows).

    A SHARED_APPS model's physical table lives in the ``public`` schema and holds
    EVERY tenant's rows; a tenant-schema request's ``search_path`` includes
    ``public``, so an unscoped changelist on such a model would render all
    schools' data on one school's branded ``/admin/``. This mixin — applied
    automatically by :meth:`TenantAdminSite.register` to every registered model
    that has a concrete ``school`` field — appends ``school == request.school OR
    school IS NULL`` so a school sees its own rows plus platform-global (NULL)
    rows, and NEVER another tenant's. It WRAPS (via ``super()``) any existing
    ``get_queryset`` so annotations / ordering are preserved. A ModelAdmin can
    opt out with ``tenant_scope_exempt = True`` (e.g. a genuinely global catalog
    the school is meant to browse in full).
    """

    _rmc_tenant_scoped = True

    def get_queryset(self, request):
        from django.db.models import Q

        qs = super().get_queryset(request)
        school = getattr(request, "school", None)
        if school is not None:
            qs = qs.filter(Q(school=school) | Q(school__isnull=True))
        return qs


@functools.lru_cache(maxsize=1)
def _tenancy_app_lists():
    """(SHARED_APPS, TENANT_APPS) parsed from config/settings.py SOURCE.

    See TenantAdminSite._model_is_schema_isolated for why this cannot read the
    live settings object. Pure ``ast``; returns ((), ()) if anything goes wrong,
    which callers treat as "unknown", never as "isolated".
    """
    import ast as _ast
    import pathlib as _pathlib

    try:
        src = _pathlib.Path(__file__).with_name("settings.py").read_text(
            encoding="utf-8", errors="ignore"
        )
        tree = _ast.parse(src)
    except (OSError, SyntaxError, ValueError):
        return ((), ())
    found = {"SHARED_APPS": [], "TENANT_APPS": []}
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Assign) or not isinstance(node.value, _ast.List):
            continue
        for target in node.targets:
            if isinstance(target, _ast.Name) and target.id in found:
                for elt in node.value.elts:
                    if isinstance(elt, _ast.Constant) and isinstance(elt.value, str):
                        found[target.id].append(elt.value)
    return (tuple(found["SHARED_APPS"]), tuple(found["TENANT_APPS"]))


# ──────────────────────────────────────────────────────────────────────────
# SHARED models with NO ``school`` field.
#
# _TenantScopedQuerysetMixin can only be applied to a model that HAS a concrete
# ``school`` field, because that is the column it filters on. A SHARED_APPS model
# WITHOUT one therefore received no changelist scoping at all -- and its table
# lives in ``public``, which a tenant-schema request's search_path includes. An
# audit of the live registry found 53 such registrations: one school's admin
# could read, filter and CSV-export every tenant's AuditLog, AccessLog,
# UserActivitySession and ComplianceReport, and mutate the platform-global
# ThreatDetectionConfig / IPAccessRule / CountryAccessRule perimeter.
#
# Every one of them is classified below, in exactly one of four ways. An
# unclassified model FAILS CLOSED (see ``_tenant_scoped_admin_class``): a
# changelist nobody has reasoned about must render nothing rather than silently
# render every tenant's rows, which is the same fail-closed stance
# _TenantFormFKScopeMixin already takes for an indeterminate School picker.

# (a) Genuinely global catalogs. A school is MEANT to browse the whole list --
#     platform permission codes, region compliance requirements, blueprint
#     templates, report-card styles. Not a leak; browsing is the feature.
TENANT_ADMIN_GLOBAL_CATALOGS = frozenset({
    "accounts.Permission",
    "auth.Group",
    "brand_experience.ThemePack",
    "compliance.CertificateTemplate",
    "compliance.ComplianceRule",
    "compliance.LegalDocument",
    "compliance.RegionFeatureCompliance",
    "compliance.RegionalComplianceRequirement",
    "compliance.StudentIDFormat",
    "emis.EMISCompliance",       # keyed by country_code/ministry, not by school
    "emis.EMISFieldMapping",     # country-keyed export field catalog
    "global_registries.GradingScaleConfig",
    "global_registries.HolidayCalendar",
    "global_registries.WeatherLocation",
    "metadata.EntityCatalogEntry",
    "runtime_blueprints.DashboardLayout",
    "runtime_blueprints.DashboardPack",
    "runtime_blueprints.DashboardTemplate",
    "runtime_blueprints.DashboardWidget",
    "runtime_blueprints.WorkflowPack",
    "runtime_blueprints.WorkflowTemplate",
    "siteconfig.FeatureToggleDefinition",
    # A singleton with no school column, and its tenant-admin placement is
    # DELIBERATE: two tests -- accounts test_site_settings_tenant_admin_only_
    # platform_uses_super and platform_runtime test_site_settings_on_tenant_
    # admin_only -- assert it is on the tenant site and NOT the platform one,
    # because the operator has its own surface at super:site_settings_*.
    #
    # It is listed here rather than scoped because there is nothing to scope: one
    # row, no school. Worth an operator's attention rather than a silent entry --
    # its `maintenance_mode` is the PLATFORM-DEFAULT layer of a cascade
    # (RuntimeDefaults -> School.settings -> here; see
    # siteconfig/domain_ownership.py, which labels it "safe_platform_default"),
    # and MaintenanceModeMiddleware resolves the EFFECTIVE value per tenant. So a
    # tenant admin editing this row moves the default that every school which has
    # NOT overridden it will inherit. That is a product decision about who may
    # edit a shared default, not a scoping bug, and it is reported rather than
    # changed here.
    "siteconfig.SiteSettings",
    "siteconfig.GlobalSyllabus",
    "siteconfig.ReportCardStyle",
    "siteconfig.ReportTemplate",
})

# (b) Reachable from a school by a relation path. Same shape as the school-field
#     mixin, one join further out.
TENANT_ADMIN_RELATION_SCOPE = {
    "schools.DonorGiftAccessLink": "donor__school",
    "siteconfig.WorkflowRunLog": "tenant_workflow__school",
}

# (c) Rows about a PERSON, with no school of their own -- audit trails,
#     delegations, per-user preferences. The only tenant signal is who the actor
#     is, so the row belongs to this school when that actor is a member of it.
#     A row whose actor is NULL (system-initiated) is deliberately NOT shown to
#     any tenant: it cannot be attributed, and guessing would leak.
TENANT_ADMIN_ACTOR_SCOPE = {
    "accounts.Delegation": "delegator",
    "accounts.DelegationActionLog": "actor",
    "accounts.TemporaryRoleGrant": "user",
    "accounts.UserPasskey": "user",
    "accounts.UserPreference": "user",
    "apicenter.APIAuditLog": "changed_by",
    "compliance.AccessLog": "user",
    "compliance.AuditLog": "user",
    "compliance.ComplianceAuditLog": "user",
    "compliance.ComplianceCheck": "checked_by",
    "compliance.ComplianceReport": "generated_by",
    "compliance.UserActivitySession": "user",
    "emis.EMISExport": "exported_by",
    "requests.RequestAudit": "actor",
    "requests.RequestDecision": "decided_by",
    "runtime_blueprints.DashboardUserPreference": "user",
    "siteconfig.DashboardUserPreference": "user",
    "siteconfig.UserPreference": "user",
}

# (d) Platform-operator surfaces that must not appear on a tenant admin at all.
#     These are not "a school's data the school may not see" -- they are the
#     PLATFORM's own security perimeter and config history. ThreatDetectionConfig
#     is a global singleton, so a tenant admin toggling it disabled threat
#     detection for every school on the platform; IPAccessRule / CountryAccessRule
#     are the platform-wide allow/deny perimeter.
TENANT_ADMIN_OPERATOR_ONLY = frozenset({
    "compliance.AuditArchiveRecord",
    "compliance.AuditLegalHold",
    "compliance.CountryAccessRule",
    "compliance.IPAccessRule",
    "compliance.ThreatDetectionConfig",
    "metadata.ConfigMutationAuditLog",
})

# (e) Already scoped by the ModelAdmin's own get_queryset. Listed here rather
#     than left to the fail-closed arm, and listed HERE rather than flagged in
#     the app so all five classifications are read in one place.
TENANT_ADMIN_SELF_SCOPED = frozenset({
    # TenantScopedUserAdmin.get_queryset filters to users_queryset_for_school
    # and returns .none() when the school is indeterminate.
    "accounts.User",
})


class _TenantUnclassifiedFailClosedMixin:
    """Render nothing for a SHARED model nobody has classified.

    Reached only when a model is in SHARED_APPS, has no ``school`` field, and
    appears in none of the four maps above. The alternative -- rendering the
    changelist unscoped -- is a cross-tenant read on a table that physically
    holds every tenant's rows, which is how 53 registrations came to leak. An
    empty changelist is visible and reportable; a full one is not.
    """

    _rmc_tenant_scoped = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        logging.getLogger(__name__).warning(
            "tenant admin: %s is a SHARED model with no school field and no "
            "tenant-scope classification; rendering empty. Classify it in "
            "config/admin.py (TENANT_ADMIN_* maps).",
            qs.model._meta.label,
        )
        return qs.none()


class _TenantRelationScopedQuerysetMixin:
    """Scope a changelist through a relation path that reaches ``school``.

    ``tenant_scope_path`` is a normal ORM lookup (``donor__school``). Fails
    CLOSED when the school is indeterminate: an unscoped fallback on a SHARED
    table is the leak this exists to prevent.
    """

    _rmc_tenant_scoped = True
    tenant_scope_path = None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        school = getattr(request, "school", None)
        path = self.tenant_scope_path
        if not path:
            return qs.none()
        if school is None:
            return qs.none()
        return qs.filter(**{path: school})


class _TenantActorScopedQuerysetMixin:
    """Scope a person-keyed changelist to actors who belong to this school.

    ``tenant_actor_path`` names the FK to the acting user. A row is this
    school's when that user holds a SchoolMembership here. Rows with a NULL
    actor are excluded: a system-initiated event carries no tenant, and showing
    it to one school would show it to all of them.

    The REQUESTING user's own rows are always included, membership or not. On a
    per-person model -- a passkey, a dashboard preference, one's own audit trail
    -- your own row is the one thing that is unambiguously yours to see, and
    excluding it leaks nothing to anybody. Without this, a platform superuser
    opening a tenant /admin/ could not reach their own preference row; two
    existing admin-smoke tests do exactly that and caught it.

    Fails CLOSED on an indeterminate school, and on any error resolving
    membership -- an admin changelist that cannot prove which tenant it is
    serving must render nothing.
    """

    _rmc_tenant_scoped = True
    tenant_actor_path = None

    def get_queryset(self, request):
        from django.db.models import Q

        qs = super().get_queryset(request)
        school = getattr(request, "school", None)
        path = self.tenant_actor_path
        if not path or school is None:
            return qs.none()
        try:
            from apps.schools.models import SchoolMembership

            # tenant-isolation-allow: request-school-scoped-membership-lookup-for-admin-changelist
            member_ids = SchoolMembership.objects.filter(school=school).values_list(
                "user_id", flat=True
            )
        except (DatabaseError, ImportError, TypeError, ValueError):
            return qs.none()

        scope = Q(**{f"{path}__in": member_ids})
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            scope |= Q(**{path: user})
        return qs.filter(scope)


class _TenantFormFKScopeMixin:
    """Scope FK / M2M OPTION LISTS in tenant ``/admin/`` add & change forms to the
    request's school — the ``formfield_for_foreignkey`` / ``formfield_for_manytomany``
    sibling of the changelist :class:`_TenantScopedQuerysetMixin`.

    A ForeignKey to the SHARED_APPS ``schools.School`` reads the ``public`` schema,
    whose single table holds EVERY tenant's rows — so an unscoped form dropdown renders
    a **cross-tenant picker** (the reported bug: Add Academic Year's ``School`` field
    listing other schools). Historically each admin had to remember a manual ``exclude``
    / override (e.g. CurriculumAllocationAdmin's ``exclude = ("school",)``); this mixin —
    applied by :meth:`TenantAdminSite.register` to EVERY registered model (a model with
    no ``school`` field of its own can still FK ``School``) — makes it structural. It
    limits the option list to:

      * ``schools.School`` FK       → the request's OWN school only (and pre-selects it);
      * a SHARED school-bearing FK   → own school + platform-global (``NULL``) rows.

    Both are safe on CHANGE forms too: an object owned by this tenant always carries its
    own School (or NULL), so the scoped queryset never rejects an existing value.
    TENANT_APPS targets are schema-isolated already, so their option lists carry only
    this tenant's rows — left untouched. ``accounts.User`` FKs are deliberately NOT
    scoped here (the tenant User surface is already confined to school members by
    ``TenantScopedUserAdmin`` + autocomplete; a blunt member-only form queryset would
    reject a legitimate existing operator-set ``created_by`` on a change form). FAIL-
    CLOSED (``.none()``) for ``School`` when the school is indeterminate: a tenant form
    must never fall back to every tenant's rows. Opt out with
    ``tenant_fk_scope_exempt = True``.
    """

    _rmc_tenant_fk_scoped = True

    def _rmc_scope_related_formfield(self, db_field, request, formfield):
        if formfield is None:
            return formfield
        qs = getattr(formfield, "queryset", None)
        related = getattr(db_field, "related_model", None)
        if qs is None or related is None:
            return formfield
        if isinstance(related, str):
            # A few legacy lazy relations retain their string declaration on
            # the field while Django has already built a usable form queryset.
            # Resolve those safely; an unresolved optional integration must not
            # make the entire tenant admin form return HTTP 500.
            from django.apps import apps as django_apps

            try:
                if "." in related:
                    related = django_apps.get_model(related, require_ready=False)
                else:
                    related = django_apps.get_model(
                        db_field.model._meta.app_label,
                        related,
                        require_ready=False,
                    )
            except (LookupError, ValueError):
                return formfield

        is_school = related._meta.label_lower == "schools.school"
        is_school_bearing = TenantAdminSite._model_has_concrete_school_field(related)
        if not (is_school or is_school_bearing):
            # TENANT_APPS / genuinely global catalog / User target — either
            # schema-isolated or scoped by its own admin. Leave untouched.
            return formfield

        from django.db.models import Q

        school = getattr(request, "school", None)
        determinate = (
            school is not None
            and getattr(school, "pk", None) is not None
            and school.__class__.__name__ == "School"
        )

        if is_school:
            if not determinate:
                # Fail closed: never fall back to every tenant's school.
                formfield.queryset = qs.none()
                return formfield
            formfield.queryset = qs.filter(pk=school.pk)
            # Pre-select the tenant's own school (the school comes from the tenant
            # context / header switcher, not a per-form choice).
            if getattr(formfield, "initial", None) in (None, ""):
                formfield.initial = school.pk
        elif is_school_bearing and determinate:
            formfield.queryset = qs.filter(Q(school=school) | Q(school__isnull=True))
        return formfield

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        return self._rmc_scope_related_formfield(db_field, request, formfield)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        return self._rmc_scope_related_formfield(db_field, request, formfield)


class TenantAdminSite(BaseRunMyCampusAdminSite):
    login_form = AuthenticationForm
    login_template = "auth/tenant_admin_login.html"
    site_header = "School configuration"
    site_title = "School configuration"
    index_title = "Configuration & records"
    index_template_name = "admin/index_tenant.html"

    def each_context(self, request):
        context = super().each_context(request)
        school = getattr(request, "school", None)
        school_name = ""
        if school is not None:
            school_name = (
                getattr(school, "name", None)
                or getattr(school, "display_name", None)
                or getattr(school, "slug", None)
                or ""
            )
        if school_name:
            context["site_header"] = school_name
            context["site_title"] = school_name
            context["index_title"] = f"{school_name} · Configuration & records"
        else:
            context["site_header"] = self.site_header
            context["site_title"] = self.site_title
            context["index_title"] = self.index_title
        context["tenant_admin_engine"] = True
        return context

    def index(self, request, extra_context=None):
        """School configuration engine index — operator-quality canvas, school-scoped."""
        base = self.each_context(request)
        context = build_admin_dashboard_context(
            request,
            base_context=base,
            title=base.get("index_title") or self.index_title,
        )
        app_list = self.get_app_list(request)
        context["app_list"] = app_list
        try:
            from apps.siteconfig.platform_admin_catalog import build_platform_admin_catalog

            context["admin_catalog"] = build_platform_admin_catalog(app_list)
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            logging.getLogger(__name__).warning(
                "tenant admin catalog build failed", exc_info=True
            )
            context["admin_catalog"] = {
                "entries": [],
                "sections": [],
                "model_count": 0,
                "app_count": 0,
                "section_count": 0,
            }
        context["tenant_engine_kpis"] = self._tenant_engine_kpis(request)
        if extra_context:
            context.update(extra_context)
        return TemplateResponse(request, self.index_template_name, context)

    @staticmethod
    def _tenant_engine_kpis(request) -> dict:
        """Approval HTML Surface 1 metrics: staff / readiness / pending invites."""
        school = getattr(request, "school", None)
        staff_accounts = 0
        pending_invites = 0
        if school is None:
            return {
                "staff_accounts": 0,
                "config_readiness_pct": 0,
                "pending_invites": 0,
            }
        try:
            from apps.schools.models import SchoolMembership

            # tenant-isolation-allow: request-school-scoped-membership-count-for-admin-kpi
            staff_accounts = SchoolMembership.objects.filter(
                school=school,
                suspended_at__isnull=True,
            ).count()
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            staff_accounts = 0
        try:
            from apps.portal.models import PendingGuardianInvite

            # tenant-isolation-allow: request-school-scoped-via-student-fk-for-admin-kpi
            pending_invites = PendingGuardianInvite.objects.filter(
                student__school=school,
                claimed_at__isnull=True,
            ).count()
        except _ADMIN_CONTEXT_FALLBACK_ERRORS:
            pending_invites = 0
        # Readiness: coarse school-config signal (name + staff + catalog presence).
        score = 0
        if getattr(school, "name", None) or getattr(school, "slug", None):
            score += 40
        if staff_accounts > 0:
            score += 40
        if getattr(school, "schema_name", None) or getattr(school, "slug", None):
            score += 20
        return {
            "staff_accounts": staff_accounts,
            "config_readiness_pct": min(100, score),
            "pending_invites": pending_invites,
        }

    def has_permission(self, request):
        if self._is_platform_host(request):
            return False
        return tenant_admin_user_has_access(request)

    # --- Tenant isolation on the admin changelist ------------------------------
    # SHARED_APPS models registered here read the public schema (every tenant's
    # rows in one table), so without scoping a school's /admin/ would list all
    # schools' data. register() auto-wraps any school-bearing model with
    # _TenantScopedQuerysetMixin — a single structural seal instead of a
    # per-ModelAdmin get_queryset each app could (and did) forget. TENANT_APPS
    # models are schema-isolated already; the extra filter there is a harmless
    # no-op (their rows carry this school or NULL).
    @staticmethod
    def _model_is_schema_isolated(model) -> bool:
        """True when the model's app is TENANT_APPS-only.

        Its table then exists solely inside a tenant schema under
        django-tenants, and is confined by RLS in single-schema mode -- so an
        unscoped changelist on it cannot cross tenants and needs no mixin.

        Parsed from the SOURCE of config/settings.py, not read off the settings
        module or object. SHARED_APPS / TENANT_APPS are only ASSIGNED inside the
        ``if USE_DJANGO_TENANTS and postgresql`` branch, so under any other
        configuration -- which includes local dev, the SQLite test settings and
        every RLS/edge deployment -- both names are simply absent. Reading them
        at runtime therefore returns nothing, every model reads as "not
        isolated", and the fail-closed arm blanks ~89 legitimate tenant
        changelists. That is not hypothetical: this method was written that way
        first, and 89 registrations went empty.

        The two lists are the platform's canonical tenancy declaration whether
        or not the branch that assigns them executes, so the source is the
        honest place to read them.
        """
        from django.apps import apps as _django_apps

        try:
            module = _django_apps.get_app_config(model._meta.app_label).name
        except LookupError:
            return False

        shared, tenant = _tenancy_app_lists()
        if not tenant:
            # Could not read the declaration at all -- say nothing rather than
            # claim isolation the deployment may not have.
            return False

        def _has(pool):
            for entry in pool:
                mod = entry.split(".apps.")[0] if ".apps." in entry else entry
                if mod == module:
                    return True
            return False

        return bool(_has(tenant) and not _has(shared))

    @staticmethod
    def _model_has_concrete_school_field(model) -> bool:
        try:
            field = model._meta.get_field("school")
        except Exception:  # noqa: BLE001 — FieldDoesNotExist / unusual meta → not scopable
            return False
        return bool(getattr(field, "concrete", False)) and not getattr(
            field, "many_to_many", False
        )

    def _tenant_scoped_admin_class(self, model, admin_class):
        mixins = []
        # (1) FK / M2M form-field scope — applies to EVERY tenant model, because a
        #     model with no ``school`` field of its own can still ForeignKey the
        #     SHARED ``schools.School`` / ``accounts.User`` (the Add-Academic-Year
        #     School-picker leak). Structural seal for the form path.
        if not getattr(admin_class, "tenant_fk_scope_exempt", False) and not getattr(
            admin_class, "_rmc_tenant_fk_scoped", False
        ):
            mixins.append(_TenantFormFKScopeMixin)
        # (2) Changelist queryset scope.
        attrs = {}
        label = f"{model._meta.app_label}.{model.__name__}"
        already = getattr(admin_class, "tenant_scope_exempt", False) or getattr(
            admin_class, "_rmc_tenant_scoped", False
        )
        if not already:
            if self._model_has_concrete_school_field(model):
                # A SHARED model whose public table holds every tenant's rows,
                # and which carries the column to filter on.
                mixins.append(_TenantScopedQuerysetMixin)
            elif label in TENANT_ADMIN_RELATION_SCOPE:
                mixins.append(_TenantRelationScopedQuerysetMixin)
                attrs["tenant_scope_path"] = TENANT_ADMIN_RELATION_SCOPE[label]
            elif label in TENANT_ADMIN_ACTOR_SCOPE:
                mixins.append(_TenantActorScopedQuerysetMixin)
                attrs["tenant_actor_path"] = TENANT_ADMIN_ACTOR_SCOPE[label]
            elif label in TENANT_ADMIN_GLOBAL_CATALOGS:
                # Deliberately unscoped: browsing the whole catalog is the point.
                pass
            elif label in TENANT_ADMIN_SELF_SCOPED:
                # The ModelAdmin scopes itself; wrapping it would double-filter.
                pass
            elif self._model_is_schema_isolated(model):
                # TENANT_APPS: its table exists only inside this tenant's schema
                # under django-tenants, and RLS confines it in single-schema mode.
                pass
            else:
                # Unclassified SHARED model with no school column. Render
                # nothing rather than every tenant's rows -- the same
                # fail-closed stance _TenantFormFKScopeMixin takes for an
                # indeterminate School picker. Classify it in one of the four
                # maps above; scripts/scan_unscoped_shared_tenant_admin.py
                # fails CI until you do.
                mixins.append(_TenantUnclassifiedFailClosedMixin)
        if not mixins:
            return admin_class
        return type(
            admin_class.__name__,
            (*mixins, admin_class),
            {**attrs, "__module__": getattr(admin_class, "__module__", __name__)},
        )

    def register(self, model_or_iterable, admin_class=None, **options):
        """Register, auto-scoping any school-bearing model to the current tenant.

        Every tenant-admin registration path funnels through here
        (``@admin.register(..., site=tenant_admin_site)``, ``register_tenant_admin``,
        ``register_both``), so this is the one place the cross-tenant leak is
        sealed. Options are applied into the class before wrapping so Unfold's
        registration sees the final class; ``super().register`` (Unfold) still
        runs for its own bookkeeping.
        """
        from django.contrib.admin import ModelAdmin as _DjangoModelAdmin

        if isinstance(model_or_iterable, (list, tuple, set, frozenset)):
            models_iter = list(model_or_iterable)
        else:
            models_iter = [model_or_iterable]

        base_class = admin_class or _DjangoModelAdmin
        for model in models_iter:
            label = f"{model._meta.app_label}.{model.__name__}"
            if label in TENANT_ADMIN_OPERATOR_ONLY:
                # Not a school's data at all -- the PLATFORM's security
                # perimeter and config history. register_both() would otherwise
                # put ThreatDetectionConfig (a global singleton) on every
                # school's admin, where one tenant could disable threat
                # detection for all of them. Handled here rather than at each
                # call site so the decision lives in one reviewed place.
                #
                # REDIRECTED, not dropped. ThreatDetectionConfig, IPAccessRule,
                # CountryAccessRule and siteconfig.SiteSettings were registered
                # ONLY on the tenant site, so skipping them would have deleted
                # the platform's own access to its security perimeter -- turning
                # a leak into an outage. Re-home each on the platform admin
                # unless it is already there.
                try:
                    platform_admin_site.register(model, base_class)
                except AlreadyRegistered:
                    pass
                except Exception:  # noqa: BLE001 — a re-home must never break startup
                    logging.getLogger(__name__).exception(
                        "tenant admin: could not re-home operator-only model %s "
                        "onto the platform admin", label,
                    )
                continue
            cls = base_class
            if options:
                cls = type(
                    f"{model.__name__}Admin",
                    (base_class,),
                    {**options, "__module__": getattr(base_class, "__module__", __name__)},
                )
            super().register(model, self._tenant_scoped_admin_class(model, cls))


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


tenant_admin_site = TenantAdminSite(name="tenant_admin")
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
    """Register on both tenant and platform admin. Use platform_admin_class for a different backoffice class.

    An OPERATOR_ONLY model gets the platform registration only. Doing the skip
    HERE as well as in TenantAdminSite.register is not redundant: the tenant
    site re-homes an operator-only model onto the platform admin (so a model
    registered ONLY on the tenant site does not lose its last surface), and
    without this skip that re-home would land first and make this function's own
    platform call raise AlreadyRegistered at import time.
    """
    label = f"{model._meta.app_label}.{model.__name__}"
    if label not in TENANT_ADMIN_OPERATOR_ONLY:
        tenant_admin_site.register(model, admin_class)
    platform_admin_site.register(model, platform_admin_class or admin_class)
