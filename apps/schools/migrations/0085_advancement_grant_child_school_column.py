"""Give the advancement/grant CHILD tables their own tenant column.

``AdvancementGift``, ``DonorGiftAccessLink``, ``GrantMilestone`` and
``GrantReport`` reached their tenant only through a parent FK
(``donor -> AdvancementDonor.school``, ``grant -> GrantApplication.school``).
An RLS policy is keyed on ``school_id``, so a table without that column can
never have one -- and ``scripts/scan_rls_table_coverage.py`` skips any model
without a ``school`` field, so the zero-baseline gate could not see them either.
Under ``USE_DJANGO_TENANTS=0`` RLS *is* the tenant boundary (settings.py), so a
query that forgot ``donor__school_id`` read every tenant's gift amounts and
donor names with no database backstop.

Added nullable, backfilled from the parent, then tightened to NOT NULL so the
policy in the companion ``*_rls_*`` migration can never see a NULL tenant.
"""

from django.db import migrations, models
import django.db.models.deletion

_PARENTS = (
    ("AdvancementGift", "donor"),
    ("DonorGiftAccessLink", "donor"),
    ("GrantMilestone", "grant"),
    ("GrantReport", "grant"),
)


def backfill_school(apps, schema_editor):
    for model_name, parent in _PARENTS:
        model = apps.get_model("schools", model_name)
        parent_field = f"{parent}__school_id"
        for row in model.objects.filter(school_id__isnull=True).values(
            "pk", parent_field
        ):
            model.objects.filter(pk=row["pk"]).update(school_id=row[parent_field])


def unbackfill(apps, schema_editor):
    """Nothing to undo: the column itself is dropped by the reverse AddField."""


def _fk(null):
    return {
        "AdvancementGift": models.ForeignKey(
            null=null,
            on_delete=django.db.models.deletion.CASCADE,
            related_name="advancement_gifts",
            to="schools.school",
        ),
        "DonorGiftAccessLink": models.ForeignKey(
            null=null,
            on_delete=django.db.models.deletion.CASCADE,
            related_name="donor_gift_access_links",
            to="schools.school",
        ),
        "GrantMilestone": models.ForeignKey(
            null=null,
            on_delete=django.db.models.deletion.CASCADE,
            related_name="grant_milestones",
            to="schools.school",
        ),
        "GrantReport": models.ForeignKey(
            null=null,
            on_delete=django.db.models.deletion.CASCADE,
            related_name="grant_reports",
            to="schools.school",
        ),
    }


class Migration(migrations.Migration):
    dependencies = [("schools", "0084_alter_marketing_funnel_event_types")]

    operations = (
        [
            migrations.AddField(
                model_name=name.lower(),
                name="school",
                field=_fk(True)[name],
            )
            for name, _parent in _PARENTS
        ]
        + [migrations.RunPython(backfill_school, unbackfill)]
        + [
            migrations.AlterField(
                model_name=name.lower(),
                name="school",
                field=_fk(False)[name],
            )
            for name, _parent in _PARENTS
        ]
    )
