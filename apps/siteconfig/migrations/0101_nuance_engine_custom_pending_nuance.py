# Section 7: Multi-Tenant Extensibility & Nuance Engine — CustomNuance, PendingNuance

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0100_custom_feature_ticket_and_fragment"),
        ("schools", "0010_security_powerhouse_audit_passkey"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomNuance",
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
                    "hook_point",
                    models.CharField(
                        choices=[
                            ("tuition_calc", "Tuition / fee calculation"),
                            ("grade_weight", "Grade weighting"),
                            ("attendance_alert", "Attendance alerts"),
                            ("fee_discount", "Fee discount eligibility"),
                            ("generic", "Generic (custom)"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "logic_data",
                    models.JSONField(
                        default=dict,
                        help_text="JSON-Logic structure. Only allowed ops run.",
                    ),
                ),
                (
                    "human_description",
                    models.TextField(
                        blank=True,
                        help_text="Plain-language description (e.g. for Principal); can be AI-generated.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="custom_nuances",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "ordering": ["school", "hook_point"],
                "verbose_name": "Custom nuance",
                "verbose_name_plural": "Custom nuances",
                "unique_together": {("school", "hook_point")},
            },
        ),
        migrations.CreateModel(
            name="PendingNuance",
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
                    "hook_point",
                    models.CharField(
                        choices=[
                            ("tuition_calc", "Tuition / fee calculation"),
                            ("grade_weight", "Grade weighting"),
                            ("attendance_alert", "Attendance alerts"),
                            ("fee_discount", "Fee discount eligibility"),
                            ("generic", "Generic (custom)"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "proposed_logic",
                    models.JSONField(
                        default=dict, help_text="JSON-Logic to apply at hook_point"
                    ),
                ),
                (
                    "human_explanation",
                    models.TextField(
                        blank=True, help_text="Plain-language description for reviewer"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending review"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_nuances",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pending_nuances",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Pending nuance",
                "verbose_name_plural": "Pending nuances",
            },
        ),
    ]
