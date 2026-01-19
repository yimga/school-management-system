from django.contrib import admin

from .models import PortalFeatureItem


@admin.register(PortalFeatureItem)
class PortalFeatureItemAdmin(admin.ModelAdmin):
    list_display = ("title", "feature", "is_active", "created_by", "created_at")
    list_filter = ("feature", "is_active")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    autocomplete_fields = ("created_by",)
