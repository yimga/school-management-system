from django.contrib import admin
from .models import School, SchoolMembership


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "subdomain", "sub_system", "is_active", "created_at")
    list_filter = ("sub_system", "is_active")
    search_fields = ("name", "slug", "subdomain")
    readonly_fields = ("id", "created_at", "updated_at")
    prepopulated_fields = {"subdomain": ["slug"]}


@admin.register(SchoolMembership)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "is_primary", "created_at")
    list_filter = ("role", "school")
    search_fields = ("user__username", "school__name")
