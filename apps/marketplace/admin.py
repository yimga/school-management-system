from django.contrib import admin
from .models import (
    MarketplaceApp,
    AppScope,
    AppInstallation,
    ScopeGrant,
    AppBillingLedger,
    AppAuditLog,
    AppVersionCompat,
)


@admin.register(MarketplaceApp)
class MarketplaceAppAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "kind", "version", "is_active", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("slug", "name")


@admin.register(AppScope)
class AppScopeAdmin(admin.ModelAdmin):
    list_display = ("app", "scope_code", "description")
    list_filter = ("app",)


@admin.register(AppInstallation)
class AppInstallationAdmin(admin.ModelAdmin):
    list_display = ("app", "school", "status", "installed_at", "installed_by")
    list_filter = ("status", "app")
    search_fields = ("school__slug", "app__slug")
    raw_id_fields = ("school", "installed_by")


@admin.register(ScopeGrant)
class ScopeGrantAdmin(admin.ModelAdmin):
    list_display = ("installation", "scope", "granted_at", "granted_by")
    raw_id_fields = ("installation", "scope", "granted_by")


@admin.register(AppBillingLedger)
class AppBillingLedgerAdmin(admin.ModelAdmin):
    list_display = ("app", "school", "kind", "amount", "currency", "created_at")
    list_filter = ("kind", "currency")
    raw_id_fields = ("school", "app", "installation")


@admin.register(AppAuditLog)
class AppAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "app", "school", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("action",)
    raw_id_fields = ("installation", "school", "app", "actor")
    readonly_fields = ("created_at",)


@admin.register(AppVersionCompat)
class AppVersionCompatAdmin(admin.ModelAdmin):
    list_display = ("app", "platform_min_version", "app_version_min", "app_version_max")
