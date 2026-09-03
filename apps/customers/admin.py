"""Operator admin for the django-tenants registry.

Both models are PLATFORM data, not tenant data: a Client is one school's schema
and a Domain is the hostname that resolves to it, so they belong on the operator
host and nowhere else. They are registered with an explicit ``site=`` because
Django's default ``admin.site`` is mounted by no urlconf in this repo -- a bare
``@admin.register(Model)`` here produced two screens that no host could open, and
``SHOW_PUBLIC_IF_NO_TENANT_FOUND`` means a MISSING Domain row silently serves the
marketing site to a paying tenant with no UI anywhere to add the row back.
"""

from django.apps import apps as django_apps
from django.contrib import admin

from config.admin import platform_admin_site

# ``TenantAdminMixin`` is a ONE-ATTRIBUTE class: it sets
# ``change_form_template = 'admin/django_tenants/tenant/change_form.html'``
# and nothing else. That template ships only inside the django_tenants
# PACKAGE, and settings.py adds "django_tenants" to INSTALLED_APPS solely
# inside ``if USE_DJANGO_TENANTS and postgresql``. Everywhere that block does
# not run -- a sovereign edge box (.env.edge.example sets
# USE_DJANGO_TENANTS=0), any RLS deployment, and every developer machine on
# SQLite -- the app-directories loader has no directory to find it in, so
# Platform Backoffice -> Clients -> add/change raised TemplateDoesNotExist.
# Reproduced 2026-08-31 on the dev DB; the Render cloud sets
# USE_DJANGO_TENANTS=1 on PostgreSQL and was never affected.
#
# The condition is the app registry, NOT ``settings.USE_DJANGO_TENANTS``:
# an explicit ``TENANCY_MODE=SCHEMA`` forces that flag True (settings.py
# ~4750) while the INSTALLED_APPS block still requires PostgreSQL, so the
# flag can be True with the package absent. ``is_installed`` is true exactly
# when the template is loadable.
if django_apps.is_installed("django_tenants"):
    from django_tenants.admin import TenantAdminMixin

    _CLIENT_ADMIN_BASES = (TenantAdminMixin, admin.ModelAdmin)
else:
    _CLIENT_ADMIN_BASES = (admin.ModelAdmin,)

from .models import Client, Domain


@admin.register(Client, site=platform_admin_site)
class ClientAdmin(*_CLIENT_ADMIN_BASES):
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
