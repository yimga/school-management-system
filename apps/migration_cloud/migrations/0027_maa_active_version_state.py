"""v3.40.0 Agent 15 — MAAActiveVersionState singleton table.

CreateModel + RunPython seed of the singleton row at active_version="v1.0".
The partial UniqueConstraint(_singleton=True) ensures one row per env.

The two new audit-event-type enum values
(``migration.maa.v2_activated_by_operator``,
``migration.data_retention.purge_applied``) are choices-only changes on
``MigrationCloudAuditEvent.event_type``; Django generates no schema diff
for TextChoices additions when the underlying column type is unchanged,
so this migration omits an AlterField on that column to avoid noise.
"""
from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _seed_singleton(apps, schema_editor):
    Model = apps.get_model("migration_cloud", "MAAActiveVersionState")
    # tenant-isolation-allow: platform-wide-maa-active-version-singleton-seed
    if not Model.objects.filter(_singleton=True).exists():
        Model.objects.create(
            _singleton=True,
            active_version="v1.0",
        )


def _unseed_singleton(apps, schema_editor):
    Model = apps.get_model("migration_cloud", "MAAActiveVersionState")
    # tenant-isolation-allow: platform-wide-maa-active-version-singleton-unseed
    Model.objects.filter(_singleton=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0026_staging_rows_json"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MAAActiveVersionState",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "_singleton",
                    models.BooleanField(
                        default=True,
                        editable=False,
                        help_text="Always True; together with the partial unique index this enforces one-row-per-env.",
                    ),
                ),
                (
                    "active_version",
                    models.CharField(
                        default="v1.0",
                        help_text="The currently-binding MAA version. Defaults to v1.0.",
                        max_length=16,
                    ),
                ),
                (
                    "counsel_signoff_pdf_url",
                    models.TextField(
                        blank=True,
                        null=True,
                        help_text=(
                            "URL the operator pasted in after counsel signed the v2.0 PDF. "
                            "May contain a presigned token; NEVER logged."
                        ),
                    ),
                ),
                (
                    "counsel_attestation_sha256",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        null=True,
                        help_text=(
                            "sha256(counsel_attestation_text.encode('utf-8')) — fingerprint "
                            "of the operator's verbatim attestation. Raw text is NEVER "
                            "persisted; only the fingerprint."
                        ),
                    ),
                ),
                (
                    "counsel_attestation_name",
                    models.CharField(
                        blank=True,
                        max_length=256,
                        null=True,
                        help_text="Full legal name of operator confirming counsel has signed.",
                    ),
                ),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "activated_by_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="maa_active_version_activations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Operator internal commentary; not surfaced to tenants.",
                    ),
                ),
            ],
            options={
                "verbose_name": "MAA active version state",
                "verbose_name_plural": "MAA active version state",
            },
        ),
        migrations.AddConstraint(
            model_name="maaactiveversionstate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("_singleton", True)),
                fields=("_singleton",),
                name="maa_active_version_singleton",
            ),
        ),
        migrations.RunPython(_seed_singleton, reverse_code=_unseed_singleton),
    ]
