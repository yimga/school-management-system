from django.contrib import admin

from apps.social_media.models import (
    SocialCampaignAttribution,
    SocialMediaIntegration,
    SocialModerationItem,
    SocialPostOutbox,
)


@admin.register(SocialMediaIntegration)
class SocialMediaIntegrationAdmin(admin.ModelAdmin):
    list_display = ("provider", "school", "handle", "is_active", "needs_reauth", "feed_cached_at")
    list_filter = ("provider", "is_active", "needs_reauth")
    search_fields = ("handle",)
    readonly_fields = ("feed_cache_json", "audit_log", "created_at", "updated_at")


@admin.register(SocialPostOutbox)
class SocialPostOutboxAdmin(admin.ModelAdmin):
    list_display = ("integration", "school", "status", "priority", "created_at")
    list_filter = ("status", "priority")


@admin.register(SocialModerationItem)
class SocialModerationItemAdmin(admin.ModelAdmin):
    list_display = ("school", "status", "hashtag", "created_at")
    list_filter = ("status",)


@admin.register(SocialCampaignAttribution)
class SocialCampaignAttributionAdmin(admin.ModelAdmin):
    list_display = ("school", "provider", "utm_campaign", "amount_cents", "recorded_at")
