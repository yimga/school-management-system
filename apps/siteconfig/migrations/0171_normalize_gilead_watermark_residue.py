"""
Replace Gilead-era watermark text in seeded ReportCardStyle catalog rows with
generic placeholders that respect the multi-tenant rebrand.

Background: migrations 0078 (seed_reportcard_style_catalog) and 0010
(reportcardstyle_defaults) seeded watermark_text values like "Gilead System"
and "Gilead Technical High" into the platform-wide ReportCardStyle catalog.
These are runtime-visible on every fresh deploy because the catalog is
re-seeded if rows are missing. Tenants who never customized their watermark
saw "Gilead Technical High" on their printed report cards.

This migration:
- Updates any ReportCardStyle row whose watermark_text contains "Gilead"
  to a generic placeholder ("Official report card" / "Report card") so
  tenants get a neutral default they can then customize.
- Idempotent and reversible.
"""
from django.db import migrations


def _normalize_gilead_watermark_text(apps, schema_editor):
    ReportCardStyle = apps.get_model("siteconfig", "ReportCardStyle")
    for row in ReportCardStyle.objects.exclude(watermark_text__isnull=True):
        text = (row.watermark_text or "").strip()
        if not text:
            continue
        if "gilead" not in text.lower():
            continue
        # Choose a generic replacement based on the slug if available.
        # Defaults to "Official report card" which is neutral and prints well.
        slug = (getattr(row, "slug", "") or "").lower()
        if slug.startswith("technical") or "tech" in slug:
            row.watermark_text = "Technical report card"
        elif slug.startswith("annual") or "annual" in slug:
            row.watermark_text = "Annual report card"
        else:
            row.watermark_text = "Official report card"
        row.save(update_fields=["watermark_text"])


def _noop_reverse(apps, schema_editor):
    """Reverse is a no-op — we don't restore Gilead-era text."""
    return


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0170_schoolworkflowexecutionlog_context_snapshot"),
    ]
    operations = [
        migrations.RunPython(
            _normalize_gilead_watermark_text,
            reverse_code=_noop_reverse,
        ),
    ]
