from django.contrib import admin

from config.admin import admin_site

from .models import School, SchoolMembership


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
