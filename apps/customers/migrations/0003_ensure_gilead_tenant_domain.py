# Ensure default Gilead school has Client and Domain so gilead-school.runmycampus.com
# resolves when USE_DJANGO_TENANTS=1. Run with migrate_schemas --shared.

import os
from django.db import migrations


DEFAULT_SLUG = "gilead-school"
DEFAULT_SUBDOMAIN = "gilead-school"


def _get_base_domain() -> str:
    base = (os.getenv("MULTI_TENANT_BASE_DOMAIN") or "").strip().lower()
    return base if base else "runmycampus.com"


def _normalize_schema_name(slug: str, max_length: int = 63) -> str:
    s = (slug or "").strip().lower().replace("-", "_")
    for c in s:
        if c != "_" and not c.isalnum():
            s = s.replace(c, "_")
    return s[:max_length] or "tenant"


def ensure_gilead_tenant_domain(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    School = apps.get_model("schools", "School")
    Client = apps.get_model("customers", "Client")
    Domain = apps.get_model("customers", "Domain")
    school = School.objects.filter(slug=DEFAULT_SLUG, is_active=True).first()
    if not school:
        return
    schema_name = _normalize_schema_name(DEFAULT_SLUG)
    subdomain = (getattr(school, "subdomain", None) or DEFAULT_SUBDOMAIN).strip().lower()
    base_domain = _get_base_domain()
    domain_fqdn = f"{subdomain}.{base_domain}".lower()

    client, _ = Client.objects.get_or_create(
        schema_name=schema_name,
        defaults={
            "name": getattr(school, "name", "Gilead School System Management System"),
            "school_id": school.pk,
        },
    )
    if not client.school_id:
        client.school_id = school.pk
        client.save(update_fields=["school_id"])

    Domain.objects.get_or_create(
        domain=domain_fqdn,
        defaults={"tenant_id": client.pk, "is_primary": True},
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0002_alter_client_schema_name"),
        ("schools", "0012_seed_default_gilead_school"),
    ]

    operations = [
        migrations.RunPython(ensure_gilead_tenant_domain, noop),
    ]
