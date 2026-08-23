"""Backfill ``GradeScaleRegistry.country_code`` on already-migrated databases.

Both production writers — ``ensure_grade_scale_seed`` and the ``0008`` data
migration — copied every key of ``GRADE_SCALE_SEED_DEFAULTS`` into the row
EXCEPT ``country_code``, so the five country-bound scales (UK_GCSE_9_1,
GERMAN_1_6, CBSE_10, FRENCH_0_20, US_LETTER) kept the model default ``''``.
That killed step 4 of ``resolve_grade_scale_for_tenant`` — the country fallback,
and the resolver's only per-tenant differentiator, since steps 1-2 need operator
created override rows and step 3 is a platform-wide singleton.

``0008`` is ``update_or_create``-idempotent but will not re-run on a database
that already applied it, hence this forward-only backfill. It writes
``country_code`` and nothing else, so an operator who deliberately re-pointed a
seeded scale's other columns keeps those edits.
"""

from __future__ import annotations

from django.db import migrations


def backfill_country_codes(apps, schema_editor):
    GradeScaleRegistry = apps.get_model("registries", "GradeScaleRegistry")
    # Pure-data constant (no model references) — safe to import at run time.
    from apps.registries.services import GRADE_SCALE_SEED_DEFAULTS

    for row in GRADE_SCALE_SEED_DEFAULTS:
        country_code = row.get("country_code", "")
        if not country_code:
            continue
        GradeScaleRegistry.objects.filter(code=row["code"]).exclude(
            country_code=country_code
        ).update(country_code=country_code)


class Migration(migrations.Migration):

    dependencies = [
        ("registries", "0013_education_level_isced_and_tier"),
    ]

    operations = [
        migrations.RunPython(backfill_country_codes, migrations.RunPython.noop),
    ]
