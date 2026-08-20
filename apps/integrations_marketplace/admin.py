from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from config.admin import register_both, register_platform_admin, tenant_admin_user_has_access

from .models import (
    AppAuditLog,
    AppBillingLedger,
    AppInstallation,
    AppScope,
    AppVersionCompat,
    CapabilityRegistry,
    Integration,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    PublisherOrganization,
    ScopeGrant,
    ServiceIntegration,
)


class ProxyOwnerAdmin(admin.ModelAdmin):
    list_display = ("record_key", "proxy_owner_label")

    @admin.display(description="PK")
    def record_key(self, obj):
        return obj.pk

    @admin.display(description="Record")
    def proxy_owner_label(self, obj):
        return str(obj)


class TenantIntegrationAdminMixin:
    """Tenant /admin/ integration models: owners and admin-like roles may view/change."""

    def _uses_platform_admin_site(self):
        detector = getattr(self.admin_site, "is_platform_site", None)
        return bool(callable(detector) and detector())

    def _tenant_integration_access(self, request):
        return tenant_admin_user_has_access(request)

    def has_module_permission(self, request):
        if self._uses_platform_admin_site():
            return super().has_module_permission(request)
        return self._tenant_integration_access(request)

    def has_view_permission(self, request, obj=None):
        if self._uses_platform_admin_site():
            return super().has_view_permission(request, obj)
        return self._tenant_integration_access(request)

    def has_change_permission(self, request, obj=None):
        if self._uses_platform_admin_site():
            return super().has_change_permission(request, obj)
        return self._tenant_integration_access(request)

    def has_add_permission(self, request):
        if self._uses_platform_admin_site():
            return super().has_add_permission(request)
        return self._tenant_integration_access(request)

    def has_delete_permission(self, request, obj=None):
        if self._uses_platform_admin_site():
            return super().has_delete_permission(request, obj)
        return False


class MarketplaceAppAdmin(ProxyOwnerAdmin):
    """Catalog posture columns on platform marketplace apps (batch 15 #145)."""

    change_form_template = "admin/integrations_marketplace/marketplaceapp/change_form.html"

    list_display = (
        "record_key",
        "app_slug",
        "app_name",
        "app_kind",
        "app_version",
        "app_is_active",
    )

    @admin.display(description="Slug")
    def app_slug(self, obj):
        return getattr(obj, "slug", "") or ""

    @admin.display(description="Name")
    def app_name(self, obj):
        return getattr(obj, "name", "") or ""

    @admin.display(description="Kind")
    def app_kind(self, obj):
        return getattr(obj, "kind", "") or ""

    @admin.display(description="Version")
    def app_version(self, obj):
        return getattr(obj, "version", "") or ""

    @admin.display(description="Active", boolean=True)
    def app_is_active(self, obj):
        return bool(getattr(obj, "is_active", False))


class MarketplaceListingAdmin(ProxyOwnerAdmin):
    """Readonly-friendly changelist columns + audit cross-link (batch 14 #135)."""

    change_form_template = (
        "admin/integrations_marketplace/marketplacelisting/change_form.html"
    )

    list_display = (
        "record_key",
        "listing_app_slug",
        "listing_status",
        "listing_publisher",
        "listing_short_description",
        "listing_security_review",
        "listing_certification",
        "listing_kill_switch",
        "audit_trail_link",
    )

    @admin.display(description="App slug")
    def listing_app_slug(self, obj):
        app = getattr(obj, "app", None)
        return getattr(app, "slug", "") if app is not None else ""

    @admin.display(description="Status")
    def listing_status(self, obj):
        return getattr(obj, "status", "")

    @admin.display(description="Publisher")
    def listing_publisher(self, obj):
        pub = getattr(obj, "publisher", None)
        return str(pub) if pub else "—"

    @admin.display(description="Summary")
    def listing_short_description(self, obj):
        text = (getattr(obj, "short_description", None) or "").strip()
        return text[:120] + ("…" if len(text) > 120 else "")

    @admin.display(description="Security review")
    def listing_security_review(self, obj):
        return obj.get_security_review_status_display()

    @admin.display(description="Certification")
    def listing_certification(self, obj):
        return obj.get_certification_status_display()

    @admin.display(description="Kill switch", boolean=True)
    def listing_kill_switch(self, obj):
        return bool(getattr(obj, "kill_switch_active", False))

    @admin.display(description="Audit")
    def audit_trail_link(self, obj):
        app = getattr(obj, "app", None)
        if not app or not getattr(app, "pk", None):
            return "—"
        base = reverse("admin:integrations_marketplace_appauditlog_changelist")
        return format_html(
            '<a class="text-primary-600 hover:underline" href="{}?app__id__exact={}">{}</a>',
            base,
            app.pk,
            "App audit logs",
        )


class AppVersionCompatMarketplaceAdmin(ProxyOwnerAdmin):
    """Version matrix columns after AppScope (batch 23 #260)."""

    list_display = (
        "record_key",
        "avc_app_slug",
        "avc_platform_min",
        "avc_app_min",
        "avc_app_max",
        "avc_notes",
    )

    @admin.display(description="App")
    def avc_app_slug(self, obj):
        app = getattr(obj, "app", None)
        return getattr(app, "slug", "") if app is not None else ""

    @admin.display(description="Platform min")
    def avc_platform_min(self, obj):
        return getattr(obj, "platform_min_version", "") or "—"

    @admin.display(description="App min")
    def avc_app_min(self, obj):
        return getattr(obj, "app_version_min", "") or "—"

    @admin.display(description="App max")
    def avc_app_max(self, obj):
        return getattr(obj, "app_version_max", "") or "—"

    @admin.display(description="Notes")
    def avc_notes(self, obj):
        text = (getattr(obj, "notes", None) or "").strip()
        return text[:80] + ("…" if len(text) > 80 else "")


class CapabilityRegistryMarketplaceAdmin(ProxyOwnerAdmin):
    """Capability codes at a glance after AppVersionCompat (batch 24 #275)."""

    list_display = (
        "record_key",
        "cap_code",
        "cap_name",
        "cap_category",
        "cap_active",
    )

    @admin.display(description="Code")
    def cap_code(self, obj):
        return getattr(obj, "code", "") or ""

    @admin.display(description="Name")
    def cap_name(self, obj):
        return getattr(obj, "name", "") or ""

    @admin.display(description="Category")
    def cap_category(self, obj):
        return getattr(obj, "category", "") or ""

    @admin.display(description="Active", boolean=True)
    def cap_active(self, obj):
        return bool(getattr(obj, "is_active", False))


class AppScopeMarketplaceAdmin(ProxyOwnerAdmin):
    """OAuth-style scopes: catalog + sensitivity at a glance (batch 21 #230)."""

    list_display = (
        "record_key",
        "scope_app_slug",
        "scope_code",
        "scope_description",
        "scope_sensitive",
    )

    @admin.display(description="App")
    def scope_app_slug(self, obj):
        app = getattr(obj, "app", None)
        return getattr(app, "slug", "") if app is not None else ""

    @admin.display(description="Scope")
    def scope_code(self, obj):
        return getattr(obj, "scope_code", "") or ""

    @admin.display(description="Description")
    def scope_description(self, obj):
        return (getattr(obj, "description", None) or "").strip() or "—"

    @admin.display(description="Sensitive", boolean=True)
    def scope_sensitive(self, obj):
        return bool(getattr(obj, "sensitive", False))


class PublisherOrganizationMarketplaceAdmin(ProxyOwnerAdmin):
    """Publisher registry columns after AppVersionCompat (batch 24 #275)."""

    list_display = (
        "record_key",
        "pub_name",
        "pub_slug",
        "pub_country",
        "pub_verification",
        "pub_created_at",
        "pub_updated_at",
    )

    @admin.display(description="Name")
    def pub_name(self, obj):
        return getattr(obj, "name", "") or ""

    @admin.display(description="Slug")
    def pub_slug(self, obj):
        return getattr(obj, "slug", "") or ""

    @admin.display(description="Country")
    def pub_country(self, obj):
        return (getattr(obj, "country_code", None) or "").strip() or "—"

    @admin.display(description="Verification")
    def pub_verification(self, obj):
        return getattr(obj, "verification_status", "") or ""

    @admin.display(description="Created")
    def pub_created_at(self, obj):
        ts = getattr(obj, "created_at", None)
        return ts.isoformat(timespec="seconds") if ts is not None else "—"

    @admin.display(description="Updated")
    def pub_updated_at(self, obj):
        ts = getattr(obj, "updated_at", None)
        return ts.isoformat(timespec="seconds") if ts is not None else "—"


class ScopeGrantMarketplaceAdmin(ProxyOwnerAdmin):
    """Granted scopes at a glance after MarketplaceReview (batch 26 #305)."""

    change_form_template = "admin/integrations_marketplace/scopegrant/change_form.html"

    list_display = (
        "record_key",
        "sg_app_slug",
        "sg_scope_code",
        "sg_status",
        "sg_school",
        "sg_granted_by",
        "sg_granted_at",
        "sg_elevated_at",
    )

    @admin.display(description="App")
    def sg_app_slug(self, obj):
        inst = getattr(obj, "installation", None)
        app = getattr(inst, "app", None) if inst is not None else None
        return getattr(app, "slug", "") if app is not None else ""

    @admin.display(description="Scope")
    def sg_scope_code(self, obj):
        scope = getattr(obj, "scope", None)
        return getattr(scope, "scope_code", "") if scope is not None else ""

    @admin.display(description="Status")
    def sg_status(self, obj):
        return getattr(obj, "status", "") or ""

    @admin.display(description="School")
    def sg_school(self, obj):
        inst = getattr(obj, "installation", None)
        school = getattr(inst, "school", None) if inst is not None else None
        return str(school) if school is not None else "—"

    @admin.display(description="Granted by")
    def sg_granted_by(self, obj):
        user = getattr(obj, "granted_by", None)
        if user is None:
            return "—"
        return getattr(user, "username", None) or getattr(user, "email", None) or str(
            user
        )

    @admin.display(description="Granted")
    def sg_granted_at(self, obj):
        ts = getattr(obj, "granted_at", None)
        return ts.isoformat(timespec="seconds") if ts is not None else "—"

    @admin.display(description="Elevated at")
    def sg_elevated_at(self, obj):
        ts = getattr(obj, "elevated_approved_at", None)
        return ts.isoformat(timespec="seconds") if ts is not None else "—"


class MarketplaceReviewMarketplaceAdmin(ProxyOwnerAdmin):
    """Review queue columns after PublisherOrganization (batch 25 #290)."""

    list_display = (
        "record_key",
        "mrev_app_slug",
        "mrev_type",
        "mrev_status",
        "mrev_version",
        "mrev_requested_at",
        "mrev_reviewer",
    )

    @admin.display(description="App")
    def mrev_app_slug(self, obj):
        listing = getattr(obj, "listing", None)
        app = getattr(listing, "app", None) if listing is not None else None
        return getattr(app, "slug", "") if app is not None else ""

    @admin.display(description="Review type")
    def mrev_type(self, obj):
        return getattr(obj, "review_type", "") or ""

    @admin.display(description="Status")
    def mrev_status(self, obj):
        return getattr(obj, "status", "") or ""

    @admin.display(description="App version")
    def mrev_version(self, obj):
        return (getattr(obj, "app_version", None) or "").strip() or "—"

    @admin.display(description="Requested")
    def mrev_requested_at(self, obj):
        ts = getattr(obj, "requested_at", None)
        return ts.isoformat(timespec="seconds") if ts is not None else "—"

    @admin.display(description="Reviewer")
    def mrev_reviewer(self, obj):
        user = getattr(obj, "reviewed_by", None)
        if user is None:
            return "—"
        return getattr(user, "username", None) or getattr(user, "email", None) or str(
            user
        )


class AppAuditLogMarketplaceAdmin(ProxyOwnerAdmin):
    """Install audit trail columns after ScopeGrant (batch 27 #320)."""

    list_display = (
        "record_key",
        "aal_app_slug",
        "aal_action",
        "aal_actor",
        "aal_school",
        "aal_created_at",
    )

    @admin.display(description="App")
    def aal_app_slug(self, obj):
        app = getattr(obj, "app", None)
        return getattr(app, "slug", "") if app is not None else "—"

    @admin.display(description="Action")
    def aal_action(self, obj):
        return getattr(obj, "action", "") or ""

    @admin.display(description="Actor")
    def aal_actor(self, obj):
        user = getattr(obj, "actor", None)
        if user is None:
            return "—"
        return getattr(user, "username", None) or getattr(user, "email", None) or str(
            user
        )

    @admin.display(description="School")
    def aal_school(self, obj):
        school = getattr(obj, "school", None)
        return str(school) if school is not None else "—"

    @admin.display(description="Created")
    def aal_created_at(self, obj):
        ts = getattr(obj, "created_at", None)
        return ts.isoformat(timespec="seconds") if ts is not None else "—"


class AppBillingLedgerMarketplaceAdmin(ProxyOwnerAdmin):
    """Ledger line columns after AppAuditLog (batch 28 #335)."""

    list_display = (
        "record_key",
        "abl_school",
        "abl_app_slug",
        "abl_kind",
        "abl_amount",
        "abl_currency",
        "abl_period",
        "abl_created_at",
    )

    @admin.display(description="School")
    def abl_school(self, obj):
        school = getattr(obj, "school", None)
        return str(school) if school is not None else "—"

    @admin.display(description="App")
    def abl_app_slug(self, obj):
        app = getattr(obj, "app", None)
        return getattr(app, "slug", "") if app is not None else "—"

    @admin.display(description="Kind")
    def abl_kind(self, obj):
        fn = getattr(obj, "get_kind_display", None)
        return fn() if callable(fn) else (getattr(obj, "kind", "") or "—")

    @admin.display(description="Amount")
    def abl_amount(self, obj):
        return getattr(obj, "amount", "")

    @admin.display(description="CCY")
    def abl_currency(self, obj):
        return (getattr(obj, "currency", None) or "").strip() or "—"

    @admin.display(description="Period")
    def abl_period(self, obj):
        ps = getattr(obj, "period_start", None)
        pe = getattr(obj, "period_end", None)
        if ps and pe:
            return f"{ps}–{pe}"
        if ps:
            return str(ps)
        if pe:
            return str(pe)
        return "—"

    @admin.display(description="Created")
    def abl_created_at(self, obj):
        ts = getattr(obj, "created_at", None)
        return ts.isoformat(timespec="seconds") if ts is not None else "—"


register_platform_admin(AppBillingLedger, AppBillingLedgerMarketplaceAdmin)

register_platform_admin(AppAuditLog, AppAuditLogMarketplaceAdmin)

register_platform_admin(ScopeGrant, ScopeGrantMarketplaceAdmin)
register_platform_admin(MarketplaceReview, MarketplaceReviewMarketplaceAdmin)
register_platform_admin(PublisherOrganization, PublisherOrganizationMarketplaceAdmin)

register_platform_admin(CapabilityRegistry, CapabilityRegistryMarketplaceAdmin)

register_platform_admin(AppVersionCompat, AppVersionCompatMarketplaceAdmin)
register_platform_admin(AppScope, AppScopeMarketplaceAdmin)

register_platform_admin(MarketplaceApp, MarketplaceAppAdmin)
register_platform_admin(MarketplaceListing, MarketplaceListingAdmin)


class AppInstallationMarketplaceAdmin(ProxyOwnerAdmin):
    """Tenant install posture columns (batch 17 #170 / batch 16 #155 pattern)."""

    change_form_template = (
        "admin/integrations_marketplace/appinstallation/change_form.html"
    )

    list_display = (
        "record_key",
        "inst_school",
        "inst_app_slug",
        "inst_app_name",
        "inst_installed_by",
        "inst_installed_at",
        "inst_last_health_at",
        "inst_status",
        "inst_install_phase",
        "inst_health",
    )

    @admin.display(description="School")
    def inst_school(self, obj):
        school = getattr(obj, "school", None)
        return str(school) if school is not None else "—"

    @admin.display(description="App")
    def inst_app_slug(self, obj):
        app = getattr(obj, "app", None)
        return getattr(app, "slug", "") if app is not None else ""

    @admin.display(description="App name")
    def inst_app_name(self, obj):
        app = getattr(obj, "app", None)
        return getattr(app, "name", "") if app is not None else ""

    @admin.display(description="Installed by")
    def inst_installed_by(self, obj):
        u = getattr(obj, "installed_by", None)
        if u is None:
            return "—"
        getter = getattr(u, "get_username", None)
        return getter() if callable(getter) else str(u)

    @admin.display(description="Installed")
    def inst_installed_at(self, obj):
        ts = getattr(obj, "installed_at", None)
        return ts.isoformat() if ts is not None else "—"

    @admin.display(description="Last health check")
    def inst_last_health_at(self, obj):
        ts = getattr(obj, "last_health_at", None)
        return ts.isoformat(timespec="seconds") if ts is not None else "—"

    @admin.display(description="Status")
    def inst_status(self, obj):
        return getattr(obj, "status", "") or ""

    @admin.display(description="Phase")
    def inst_install_phase(self, obj):
        return getattr(obj, "install_phase", "") or ""

    @admin.display(description="Health")
    def inst_health(self, obj):
        return (getattr(obj, "health_status", None) or "").strip() or "—"


register_platform_admin(AppInstallation, AppInstallationMarketplaceAdmin)


class ServiceIntegrationMarketplaceAdmin(TenantIntegrationAdminMixin, ProxyOwnerAdmin):
    """Tenant posture columns for school-scoped service integrations (batch 16 #155)."""

    change_form_template = (
        "admin/integrations_marketplace/serviceintegration/change_form.html"
    )

    list_display = (
        "record_key",
        "svc_school",
        "svc_name",
        "svc_type",
        "svc_active",
        "svc_has_endpoint",
    )

    @admin.display(description="School")
    def svc_school(self, obj):
        school = getattr(obj, "school", None)
        return str(school) if school is not None else "—"

    @admin.display(description="Service")
    def svc_name(self, obj):
        return getattr(obj, "service_name", "") or ""

    @admin.display(description="Type")
    def svc_type(self, obj):
        return getattr(obj, "service_type", "") or ""

    @admin.display(description="Active", boolean=True)
    def svc_active(self, obj):
        return bool(getattr(obj, "is_active", False))

    @admin.display(description="Endpoint", boolean=True)
    def svc_has_endpoint(self, obj):
        return bool((getattr(obj, "endpoint_url", None) or "").strip())


class IntegrationMarketplaceAdmin(TenantIntegrationAdminMixin, ProxyOwnerAdmin):
    """P3: escape hatch to feature control + API Center on tenant hosts."""

    list_display = (
        "record_key",
        "int_slug",
        "int_name",
        "int_provider",
        "int_category",
        "int_enabled",
        "int_health",
    )

    change_form_template = (
        "admin/integrations_marketplace/integration/change_form.html"
    )

    @admin.display(description="Slug")
    def int_slug(self, obj):
        return getattr(obj, "slug", "") or ""

    @admin.display(description="Name")
    def int_name(self, obj):
        return getattr(obj, "name", "") or ""

    @admin.display(description="Provider")
    def int_provider(self, obj):
        return getattr(obj, "provider", "") or ""

    @admin.display(description="Category")
    def int_category(self, obj):
        return getattr(obj, "category", "") or ""

    @admin.display(description="Enabled", boolean=True)
    def int_enabled(self, obj):
        return bool(getattr(obj, "enabled", False))

    @admin.display(description="Health")
    def int_health(self, obj):
        return (getattr(obj, "health_status", None) or "").strip() or "—"


register_both(Integration, IntegrationMarketplaceAdmin)
register_both(ServiceIntegration, ServiceIntegrationMarketplaceAdmin)
