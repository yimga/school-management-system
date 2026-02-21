from django.contrib import admin

from config.admin import admin_site

from .models import School, SchoolMembership, SchoolProvisioningEvent


@admin.register(School, site=admin_site)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "subdomain", "sub_system", "is_active", "created_at")
    list_filter = ("sub_system", "is_active")
    search_fields = ("name", "slug", "subdomain")
    readonly_fields = ("id", "created_at", "updated_at")
    prepopulated_fields = {"subdomain": ["slug"]}


@admin.register(SchoolMembership, site=admin_site)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "is_primary", "created_at")
    list_filter = ("role", "school")
    search_fields = ("user__username", "school__name")


@admin.register(SchoolProvisioningEvent, site=admin_site)
class SchoolProvisioningEventAdmin(admin.ModelAdmin):
    list_display = ("school", "event_type", "status", "created_at", "created_by")
    list_filter = ("event_type", "status", "school")
    search_fields = ("school__name", "event_type", "message")
    readonly_fields = ("school", "event_type", "status", "message", "payload", "created_by", "created_at")
