from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from unfold.admin import ModelAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    """Unfold-styled user admin with an additional Role field."""

    # Add role to the default Django user admin form
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Role", {"fields": ("role",)}),
    )

    # Show role in the users list
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)
