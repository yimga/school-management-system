"""Operator admin for the django-tenants registry.

Both models are PLATFORM data, not tenant data: a Client is one school's schema
and a Domain is the hostname that resolves to it, so they belong on the operator
host and nowhere else. They are registered with an explicit ``site=`` because
Django's default ``admin.site`` is mounted by no urlconf in this repo -- a bare
``@admin.register(Model)`` here produced two screens that no host could open, and
``SHOW_PUBLIC_IF_NO_TENANT_FOUND`` means a MISSING Domain row silently serves the
marketing site to a paying tenant with no UI anywhere to add the row back.
"""

from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from config.admin import platform_admin_site

from .models import Client, Domain


@admin.register(Client, site=platform_admin_site)
class ClientAdmin(TenantAdminMixin, admin.ModelAdmin):
    # db_alias is deliberately in the form (no ``fields``/``exclude``): the
    # TenantDatabaseRouter reads it to pin a tenant to a regional database and
    # this admin is its only write surface.
    list_display = ("name", "schema_name", "school", "db_alias", "created_on")
    list_filter = ("created_on",)
    search_fields = ("name", "schema_name")
    raw_id_fields = ("school",)


@admin.register(Domain, site=platform_admin_site)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("domain",)
