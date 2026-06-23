"""Local-first backfill: link region-less schools to their country's RegionConfig.

Schools created outside the signup + provisioning flow (admin, import, API) can
end up with a ``country_code`` set but no ``default_region``, so they fall back to
a generic pack instead of their country's localization. This backfill links each
such school to the RegionConfig that already exists for its country.

Read-only / non-destructive by design:

* Only touches schools where ``default_region`` is NULL (an explicit region is
  never overridden).
* Links an EXISTING RegionConfig only — never creates one (region creation stays
  in the signup/provisioning flow). A school whose country has no region row yet
  is left untouched (no regression — the generic fallback still applies; the next
  save / signal will link it once the row exists, via ``School.save``).
* ``RegionConfig.code`` is ISO alpha-3 while ``School.country_code`` is alpha-2,
  so the match goes through ``GlobalGeoCatalog.normalize_country_code`` (the exact
  normalization ``ensure_region_for_country`` used when it created the row).
"""

from __future__ import annotations

from django.db import migrations


def backfill_default_region(apps, schema_editor):
    School = apps.get_model("schools", "School")
    RegionConfig = apps.get_model("siteconfig", "RegionConfig")
    db = schema_editor.connection.alias

    # Stateless catalog (not a model) — safe to import in a data migration.
    from apps.siteconfig.global_catalog import GlobalGeoCatalog

    # The region table is tiny; index it once by its alpha-3 code.
    regions_by_code = {r.code: r for r in RegionConfig.objects.using(db).all()}
    if not regions_by_code:
        return

    region_less = (
        School.objects.using(db)
        .filter(default_region__isnull=True)
        .exclude(country_code="")
    )
    for school in region_less.iterator():
        try:
            normalized = GlobalGeoCatalog.normalize_country_code(school.country_code)
        except Exception:  # noqa: BLE001 — never abort the backfill on one bad code
            normalized = ""
        region = regions_by_code.get(normalized) if normalized else None
        if region is not None:
            School.objects.using(db).filter(pk=school.pk).update(
                default_region=region
            )


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0074_schoolmembership_is_school_owner"),
        ("siteconfig", "0099_reporttemplate_template_family"),
    ]

    operations = [
        # Forward-only data fill; reversing it would be destructive (cannot know
        # which links pre-existed), so the reverse is a deliberate no-op.
        migrations.RunPython(backfill_default_region, migrations.RunPython.noop),
    ]
