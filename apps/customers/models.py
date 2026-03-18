"""
Phase I: Tenant (Client) and Domain models for django-tenants schema-per-tenant.

When USE_DJANGO_TENANTS=1, TenantMainMiddleware resolves request.tenant to Client.
Client has a OneToOne to School so request.tenant.school gives the existing School record.
"""

from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


def _schema_name_max_length():
    return 63  # PostgreSQL schema name limit


class Client(TenantMixin):
    """
    Tenant for schema-per-tenant (django-tenants). Maps 1:1 to School.
    schema_name is used as the PostgreSQL schema (normalized from School.slug).
    """

    name = models.CharField(max_length=255)
    # Link to existing School in public schema (for display, features, settings)
    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tenant_client",
        help_text="Existing School record in public schema",
    )
    created_on = models.DateField(auto_now_add=True)
    # World Engine: optional DB alias for regional/dedicated instance (router selects DB by this).
    db_alias = models.CharField(
        max_length=63,
        blank=True,
        help_text="Optional: database alias for this tenant (e.g. region_eu, dedicated_xyz). Leave blank for default.",
    )
    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        verbose_name = "Tenant (Client)"
        verbose_name_plural = "Tenants (Clients)"


class Domain(DomainMixin):
    """Domain (hostname) for a tenant. Subdomain or custom_domain."""

    pass
