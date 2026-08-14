"""Backfill RegionConfig academic-calendar shape from the curated calendars.

``RegionConfig.academic_year_start_month`` / ``term_count_per_year`` were seeded
for only 7 countries (migration ``0090``); every other region was created with the
blunt hemisphere default (September in the north / January in the south, 3 terms).
That left the real per-country term-date calendars
(``apps/academics/country_term_calendars.py``) SILENTLY unused for every
non-standard-calendar country — an East-African January region still said
September, a US/China 2-semester region still said 3 terms, a South-Africa /
Singapore 4-term region still said 3 — so ``resolve_term_windows``'s alignment
guard declined the calendar and the school fell back to an even month split.

The runtime create path (``ensure_region_for_country``) now reads the curated
shape for freshly-created regions; this backfills the EXISTING rows to match.

Conservative, non-destructive (mirrors ``0209``'s "only touch untouched defaults"):
a row is updated ONLY when it still holds an original hemisphere default
(``term_count_per_year == 3`` AND ``academic_year_start_month`` in ``{1, 9}``) and
the curated shape actually differs. That leaves the curated exceptions untouched
(USA 8/2 has term_count 2; Uganda 2/3 has start month 2 — neither matches) and
never overrides an admin edit that changed the shape away from the default.

The shape is read from the single source of truth
(``country_calendar_shape``) rather than re-inlined, so it can never drift from
the term-date windows. The import is guarded: if the module is ever unavailable
the backfill no-ops rather than breaking a fresh-DB migration run — new regions
still get the right shape from the runtime path.
"""

from django.db import migrations

_DEFAULT_START_MONTHS = {1, 9}  # the only two values the old hemisphere default produced


def seed_region_academic_calendars(apps, schema_editor):
    try:
        from apps.academics.country_term_calendars import country_calendar_shape
    except Exception:  # noqa: BLE001 — module unavailable → skip; runtime path still covers new regions
        return

    RegionConfig = apps.get_model("siteconfig", "RegionConfig")
    for region in RegionConfig.objects.all():
        start = int(getattr(region, "academic_year_start_month", 9) or 9)
        terms = int(getattr(region, "term_count_per_year", 3) or 3)
        # Only rows still on an original hemisphere default are eligible — an
        # explicit non-default shape (curated exception or admin edit) always wins.
        if not (terms == 3 and start in _DEFAULT_START_MONTHS):
            continue
        try:
            shape = country_calendar_shape((region.code or "").strip())
        except Exception:  # noqa: BLE001 — one bad lookup never aborts the rest
            shape = None
        if not shape:
            continue
        curated_start, curated_terms = shape
        if (curated_start, curated_terms) == (start, terms):
            continue  # already correct — no write
        region.academic_year_start_month = curated_start
        region.term_count_per_year = curated_terms
        region.save(update_fields=["academic_year_start_month", "term_count_per_year"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0209_seed_region_admission_templates"),
    ]
    operations = [
        migrations.RunPython(seed_region_academic_calendars, noop_reverse),
    ]
