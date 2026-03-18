# Generated for RunMyCampus powerhouse: backfill SchoolDomain from School.subdomain and School.custom_domain

import os
from django.db import migrations


def backfill_schooldomain(apps, schema_editor):
    School = apps.get_model("schools", "School")
    SchoolDomain = apps.get_model("schools", "SchoolDomain")
    base_domain = (
        (os.getenv("MULTI_TENANT_BASE_DOMAIN") or "runmycampus.com").strip().lower()
    )
    for school in School.objects.filter(is_active=True):
        # Subdomain: subdomain.runmycampus.com
        if school.subdomain:
            domain_str = f"{school.subdomain}.{base_domain}".lower()
            if not SchoolDomain.objects.filter(
                school=school, domain=domain_str
            ).exists():
                SchoolDomain.objects.create(
                    school=school,
                    domain=domain_str,
                    kind="SUBDOMAIN",
                    is_verified=True,
                )
        # Custom domain (verified only)
        if school.custom_domain and school.custom_domain_verified:
            domain_str = school.custom_domain.strip().lower()
            if not SchoolDomain.objects.filter(
                school=school, domain=domain_str
            ).exists():
                SchoolDomain.objects.create(
                    school=school,
                    domain=domain_str,
                    kind="CUSTOM",
                    is_verified=True,
                )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0021_add_schooldomain"),
    ]

    operations = [
        migrations.RunPython(backfill_schooldomain, noop_reverse),
    ]
