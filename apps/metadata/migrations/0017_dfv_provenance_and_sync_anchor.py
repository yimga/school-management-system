"""Provenance + edge-sync anchors for the custom-field EAV pair.

Two changes with one purpose each:

*   ``DynamicFieldValue.source`` / ``source_ref`` — who last wrote a value. Measured
    on 2026-09-02: ``persist_dfv_extras`` overwrote unconditionally on re-import,
    and three human write paths (tenant EAV forms, the admin break-glass screen,
    ``set_dynamic_field_value``) were indistinguishable from an import after the
    fact, so a re-upload silently clobbered deliberate edits. ``updated_at`` is
    ``auto_now`` and advances on any write, so it cannot carry this distinction.

*   ``client_offline_id`` on both models — the standard rail anchor, so school-scoped
    custom-field definitions and values can ride the edge sync rail like every other
    registered entity (upserted by ``(school, client_offline_id)``, never by pk).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("metadata", "0016_dynamicfielddefinition_validation_json"),
    ]

    operations = [
        migrations.AddField(
            model_name="dynamicfieldvalue",
            name="source",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="dynamicfieldvalue",
            name="source_ref",
            field=models.CharField(
                blank=True,
                default="",
                help_text='Locator for the last writer, e.g. "bundle:83/artifact:12" or "user:5".',
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="dynamicfieldvalue",
            name="client_offline_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="dynamicfielddefinition",
            name="client_offline_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddConstraint(
            model_name="dynamicfieldvalue",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_offline_id", ""), _negated=True),
                fields=("school", "client_offline_id"),
                name="uniq_dfv_school_offline_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="dynamicfielddefinition",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_offline_id", ""), _negated=True),
                fields=("school", "client_offline_id"),
                name="uniq_dfd_school_offline_id",
            ),
        ),
    ]
