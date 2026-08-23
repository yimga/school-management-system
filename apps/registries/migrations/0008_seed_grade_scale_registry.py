"""Durable seed of the canonical grade-scale families.

The 9 ``GradeScaleRegistry`` families were already defined in
``apps.registries.services.GRADE_SCALE_SEED_DEFAULTS``, but nothing seeded them
at migrate time: the table was populated only opportunistically (first school
provisioning calls ``ensure_registry_baseline``) or by running the
``seed_platform_registries`` command / the coverage gate by hand. So a freshly
migrated database had an EMPTY grade-scale registry until one of those ran —
the catalog claimed 9 world scales that did not yet exist as rows.

This data migration makes the seed durable: after ``migrate`` the canonical
scales are guaranteed present. It reads the SAME single-source-of-truth constant
the service uses (no drifting copy) and writes via the *historical* model so it
stays correct regardless of later model changes. Idempotent (``update_or_create``
keyed on ``code``) and safe to re-run; reverse is a no-op because reference data
is never torn down on rollback.
"""

from __future__ import annotations

from django.db import migrations


def seed_grade_scales(apps, schema_editor):
    GradeScaleRegistry = apps.get_model("registries", "GradeScaleRegistry")
    # Pure-data constant (no model references) — safe to import at run time.
    from apps.registries.services import GRADE_SCALE_SEED_DEFAULTS

    for row in GRADE_SCALE_SEED_DEFAULTS:
        GradeScaleRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "family": row.get("family", ""),
                "country_code": row.get("country_code", ""),
                "range_definition": row.get("range_definition", {}),
                "metadata": row.get("metadata", {}),
                "sort_order": row.get("sort_order", 0),
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("registries", "0007_tenant_grade_scale_override"),
    ]

    operations = [
        migrations.RunPython(seed_grade_scales, migrations.RunPython.noop),
    ]
