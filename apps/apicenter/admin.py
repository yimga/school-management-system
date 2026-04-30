from django.contrib import admin

from django.contrib import messages

from config.admin import register_platform_admin, register_tenant_admin
from .models import (
    APIAuditLog,
    APIKey,
    APIQuota,
    DeveloperApplication,
    MarketplaceExtensionSubmission,
    OAuthAuthorizationCode,
    OAuthTokenPair,
    _hash_secret,
)


class APIKeyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "key_prefix",
        "school",
        "created_by",
        "created_at",
        "last_used_at",
        "revoked_at",
    )
    list_filter = ("revoked_at", "created_at")
    search_fields = ("name", "key_prefix")
    raw_id_fields = ("marketplace_installation",)
    readonly_fields = (
        "key_prefix",
        "secret_hash",
        "created_at",
        "last_used_at",
        "revoked_at",
    )


class APIAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "integration",
        "action",
        "changed_by",
        "reason_short",
        "ip_address",
        "created_at",
    )
    list_filter = ("action", "created_at")
    search_fields = ("reason", "integration__slug", "integration__name")
    readonly_fields = (
        "integration",
        "changed_by",
        "action",
        "reason",
        "ip_address",
        "created_at",
    )

    def reason_short(self, obj):
        return (
            (obj.reason or "")[:50] + "…"
            if len(obj.reason or "") > 50
            else (obj.reason or "—")
        )

    reason_short.short_description = "Reason"


class APIQuotaAdmin(admin.ModelAdmin):
    list_display = ("quota_type", "school", "limit_value", "period_minutes")
    list_filter = ("quota_type",)


register_tenant_admin(APIKey, APIKeyAdmin)
register_tenant_admin(APIQuota, APIQuotaAdmin)
register_tenant_admin(APIAuditLog, APIAuditLogAdmin)


class DeveloperApplicationAdmin(admin.ModelAdmin):
    list_display = ("name", "app_key", "client_id", "school", "is_active", "created_at")
    search_fields = ("name", "app_key", "client_id")
    raw_id_fields = ("marketplace_app", "school", "created_by")
    readonly_fields = ("app_key", "client_id", "client_secret_hash", "created_at")

    def save_model(self, request, obj, form, change):
        if not change:
            app_key, client_id, raw_secret = DeveloperApplication.generate_credentials()
            obj.app_key = app_key
            obj.client_id = client_id
            obj.client_secret_hash = _hash_secret(raw_secret)
            super().save_model(request, obj, form, change)
            messages.warning(
                request,
                "Copy the client secret now; it will not be shown again: "
                + raw_secret,
            )
        else:
            super().save_model(request, obj, form, change)


class OAuthTokenPairAdmin(admin.ModelAdmin):
    list_display = ("application", "user", "access_expires_at", "revoked_at", "created_at")
    readonly_fields = (
        "application",
        "user",
        "access_token_hash",
        "refresh_token_hash",
        "access_expires_at",
        "revoked_at",
        "scope",
        "created_at",
    )


class OAuthAuthorizationCodeAdmin(admin.ModelAdmin):
    list_display = ("application", "user", "expires_at", "used_at", "created_at")
    readonly_fields = ("code_hash",)


class MarketplaceExtensionSubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "state", "developer_application", "updated_at")
    list_filter = ("state",)
    search_fields = ("title", "slug")


register_platform_admin(DeveloperApplication, DeveloperApplicationAdmin)
register_platform_admin(OAuthTokenPair, OAuthTokenPairAdmin)
register_platform_admin(OAuthAuthorizationCode, OAuthAuthorizationCodeAdmin)
register_platform_admin(MarketplaceExtensionSubmission, MarketplaceExtensionSubmissionAdmin)
