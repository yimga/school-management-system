"""Admin screens for the social integration, outbox, moderation and attribution tables.

MOUNTED SITES ONLY. These four ModelAdmins were registered with a bare
``@admin.register(Model)``, i.e. on ``django.contrib.admin.site`` -- a site no
urlconf serves (``config/tenant_urls.py`` mounts ``tenant_admin_site``,
``config/manager_urls.py`` mounts ``platform_admin_site``, and ``config/urls.py``
re-resolves ``/admin/`` against one of those two). So no tenant admin and no
platform operator could open any of them from any host.

Registering through the ``config.admin`` helpers is what makes them reachable AND
safe: every tenant-admin registration funnels through ``TenantAdminSite.register``,
which wraps a school-bearing model in ``_TenantScopedQuerysetMixin`` so a tenant's
changelist shows only its own rows. Mounting the default site instead would have
opened four UNSCOPED cross-tenant CRUD screens at once.

Scope split:
  * ``SocialMediaIntegration`` / ``SocialPostOutbox`` have a NULLABLE ``school``,
    where NULL is the platform (Tier 1) corporate account. Those platform rows are
    invisible on the school-scoped tenant changelist by design, so both models also
    need the platform admin -- hence ``register_both``.
  * ``SocialModerationItem`` / ``SocialCampaignAttribution`` have a NOT NULL
    ``school``: moderation and attribution are always tenant-scoped (README), so
    they are tenant-admin only.

Secrets stay off the form. ``encrypted_oauth_token``, ``refresh_token`` and
``webhook_secret`` are ``encrypt_charfield``s that decrypt on attribute access, so
a plain ModelAdmin change form would render live OAuth credentials into HTML for
anyone who can open the page. They are excluded, and a read-only boolean reports
whether a token is present instead.
"""

from django.contrib import admin

from apps.social_media.models import (
    SocialCampaignAttribution,
    SocialMediaIntegration,
    SocialModerationItem,
    SocialPostOutbox,
)
from config.admin import register_both, register_tenant_admin

_SECRET_FIELDS = ("encrypted_oauth_token", "refresh_token", "webhook_secret")


class SocialMediaIntegrationAdmin(admin.ModelAdmin):
    list_display = ("provider", "school", "handle", "is_active", "needs_reauth", "feed_cached_at")
    list_filter = ("provider", "is_active", "needs_reauth")
    search_fields = ("handle",)
    exclude = _SECRET_FIELDS
    readonly_fields = ("feed_cache_json", "audit_log", "has_credentials", "created_at", "updated_at")

    @admin.display(boolean=True, description="Credentials stored")
    def has_credentials(self, obj):
        return bool(obj.encrypted_oauth_token)


class SocialPostOutboxAdmin(admin.ModelAdmin):
    list_display = ("integration", "school", "status", "priority", "attempts", "next_attempt_at", "created_at")
    list_filter = ("status", "priority")


class SocialModerationItemAdmin(admin.ModelAdmin):
    list_display = ("school", "status", "hashtag", "created_at")
    list_filter = ("status",)


class SocialCampaignAttributionAdmin(admin.ModelAdmin):
    list_display = ("school", "provider", "utm_campaign", "amount_cents", "recorded_at")


register_both(SocialMediaIntegration, SocialMediaIntegrationAdmin)
register_both(SocialPostOutbox, SocialPostOutboxAdmin)
register_tenant_admin(SocialModerationItem, SocialModerationItemAdmin)
register_tenant_admin(SocialCampaignAttribution, SocialCampaignAttributionAdmin)
