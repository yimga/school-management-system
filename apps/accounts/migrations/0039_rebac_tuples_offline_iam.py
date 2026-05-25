# Generated for batch 1507 — Postgres ReBAC tuples + offline IAM intents

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0001_initial"),
        ("accounts", "0038_accessrole_school_scope"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RelationshipTuple",
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
                ("subject_type", models.CharField(db_index=True, max_length=32)),
                ("subject_id", models.CharField(db_index=True, max_length=64)),
                ("relation", models.CharField(db_index=True, max_length=48)),
                ("object_type", models.CharField(db_index=True, max_length=32)),
                ("object_id", models.CharField(db_index=True, max_length=128)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("membership", "School membership"),
                            ("guardian", "StudentGuardian"),
                            ("teacher_assignment", "TeacherAssignment"),
                            ("access_role", "User.roles M2M"),
                            ("temporary_grant", "TemporaryRoleGrant"),
                            ("direct_permission", "User.feature_permissions"),
                            ("backfill", "Management command backfill"),
                        ],
                        db_index=True,
                        default="backfill",
                        max_length=32,
                    ),
                ),
                (
                    "source_key",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Stable idempotency key for writers (e.g. membership:12).",
                        max_length=128,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="relationship_tuples",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "db_table": "accounts_relationship_tuple",
                "ordering": ["school_id", "subject_type", "subject_id"],
            },
        ),
        migrations.CreateModel(
            name="OfflineAccessIntent",
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
                    "intent_type",
                    models.CharField(
                        choices=[
                            ("iam.request_access", "Request access to capability"),
                        ],
                        default="iam.request_access",
                        max_length=32,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("applied", "Applied"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=16,
                    ),
                ),
                (
                    "idempotency_key",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("server_note", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offline_access_intents",
                        to="schools.school",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offline_access_intents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "accounts_offline_access_intent",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="relationshiptuple",
            index=models.Index(
                fields=["school", "subject_type", "subject_id", "relation"],
                name="idx_rebac_subject_lookup",
            ),
        ),
        migrations.AddIndex(
            model_name="relationshiptuple",
            index=models.Index(
                fields=["school", "object_type", "object_id", "relation"],
                name="idx_rebac_object_lookup",
            ),
        ),
        migrations.AddIndex(
            model_name="relationshiptuple",
            index=models.Index(
                fields=["school", "source", "source_key"],
                name="idx_rebac_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="relationshiptuple",
            constraint=models.UniqueConstraint(
                fields=(
                    "school",
                    "subject_type",
                    "subject_id",
                    "relation",
                    "object_type",
                    "object_id",
                ),
                name="uniq_relationship_tuple_edge",
            ),
        ),
        migrations.AddConstraint(
            model_name="offlineaccessintent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__gt", "")),
                fields=("school", "idempotency_key"),
                name="uniq_offline_access_intent_idempotency",
            ),
        ),
    ]
