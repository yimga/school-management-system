# Idempotent create. A thrash-cancelled deploy can partially create
# communication_threadmessageattachment in a tenant schema while this migration is
# NOT recorded as applied (out-of-band / partial-migrate drift). A plain CreateModel
# then raises psycopg DuplicateTable ("relation already exists") and — under
# set -e in render_predeploy.sh — aborts EVERY deploy, freezing production at the
# last good commit (the same failure that platform_runtime 0092 hit).
#
# SeparateDatabaseAndState keeps the model in Django's migration state (so model
# history + makemigrations stay clean and dependents resolve), while the database
# step delegates to tenant_schema_guard.ensure_models_tables, which creates the
# table only when missing and is a no-op when it already exists.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _ensure_tables(apps, schema_editor):
    # This migration INTRODUCES ThreadMessageAttachment, so the migration-state
    # ``apps`` (from-state) does not contain it yet — get_model on it raises
    # LookupError. Resolve the concrete model from the live registry instead;
    # safe because this is the leaf migration for the model (no later schema
    # change), so the live definition equals this migration's state.
    from django.apps import apps as live_apps  # noqa: F811 — live registry, not the historical state

    from apps.schools.tenant_schema_guard import ensure_models_tables

    ensure_models_tables(
        schema_editor,
        [live_apps.get_model("communication", "ThreadMessageAttachment")],
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("communication", "0027_message_read_at"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ThreadMessageAttachment",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "file",
                            models.FileField(upload_to="thread_attachments/%Y/%m/"),
                        ),
                        ("original_name", models.CharField(max_length=255)),
                        ("content_type", models.CharField(blank=True, max_length=128)),
                        ("size_bytes", models.PositiveIntegerField(default=0)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "message",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="attachments",
                                to="communication.threadmessage",
                            ),
                        ),
                        (
                            "uploaded_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="+",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "ordering": ["created_at"],
                    },
                ),
            ],
            database_operations=[
                migrations.RunPython(_ensure_tables, migrations.RunPython.noop),
            ],
        ),
    ]
