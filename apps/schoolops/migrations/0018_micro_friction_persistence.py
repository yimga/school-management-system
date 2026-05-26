# Generated manually for batch 1510 local-first completion.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("schoolops", "0017_emaildeliveryevent_idempotency_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubstituteHandoverPacketRecord",
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
                ("packet_id", models.CharField(db_index=True, max_length=36)),
                ("teacher_id_hash", models.CharField(max_length=12)),
                ("substitute_id_hash", models.CharField(max_length=12)),
                ("valid_from", models.DateTimeField()),
                ("valid_until", models.DateTimeField()),
                ("lesson_outline", models.JSONField(blank=True, default=list)),
                ("seating_chart_ref", models.CharField(blank=True, default="", max_length=128)),
                ("medical_iep_gated", models.BooleanField(default=True)),
                ("reason_code", models.CharField(default="unspecified", max_length=64)),
                ("audit_event_id", models.CharField(blank=True, default="", max_length=36)),
                (
                    "source",
                    models.CharField(
                        choices=[("online", "Online form"), ("offline", "Offline sync")],
                        default="online",
                        max_length=16,
                    ),
                ),
                ("client_offline_id", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="substitute_handover_packets_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="substitute_handover_packets",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "db_table": "schoolops_substitute_handover_packet",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LostBelongingsTagRecord",
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
                ("asset_id", models.CharField(max_length=128)),
                ("short_code", models.CharField(max_length=32)),
                ("label_hint", models.CharField(max_length=80)),
                ("tenant_id_hash", models.CharField(max_length=12)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("recovered", "Recovered")],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("client_offline_id", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recovered_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lost_belongings_tags_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lost_belongings_tags",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "db_table": "schoolops_lost_belongings_tag",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LostBelongingsCustodyEventRecord",
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
                ("event_id", models.CharField(db_index=True, max_length=36)),
                (
                    "actor_kind",
                    models.CharField(
                        choices=[
                            ("anonymous_finder", "Anonymous finder"),
                            ("staff", "Staff"),
                        ],
                        max_length=24,
                    ),
                ),
                ("notes_redacted", models.CharField(blank=True, default="", max_length=280)),
                ("parent_notified", models.BooleanField(default=False)),
                ("staff_id_hash", models.CharField(blank=True, default="", max_length=12)),
                ("occurred_at", models.DateTimeField()),
                ("client_offline_id", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lost_belongings_custody_events",
                        to="schools.school",
                    ),
                ),
                (
                    "tag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="custody_events",
                        to="schoolops.lostbelongingstagrecord",
                    ),
                ),
            ],
            options={
                "db_table": "schoolops_lost_belongings_custody_event",
                "ordering": ["-occurred_at"],
            },
        ),
        migrations.AddIndex(
            model_name="substitutehandoverpacketrecord",
            index=models.Index(
                fields=["school", "valid_until"],
                name="schoolops_su_school__a1b2c3_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="substitutehandoverpacketrecord",
            constraint=models.UniqueConstraint(
                fields=("school", "packet_id"),
                name="uniq_handover_packet_per_school",
            ),
        ),
        migrations.AddConstraint(
            model_name="lostbelongingstagrecord",
            constraint=models.UniqueConstraint(
                fields=("school", "short_code"),
                name="uniq_lost_tag_short_code_per_school",
            ),
        ),
        migrations.AddConstraint(
            model_name="lostbelongingscustodyeventrecord",
            constraint=models.UniqueConstraint(
                fields=("school", "event_id"),
                name="uniq_custody_event_id_per_school",
            ),
        ),
    ]
