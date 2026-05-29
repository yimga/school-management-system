# Generated manually for global governance Phase 4B

import uuid

import apps.accounts.models
import apps.governance.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("governance", "0002_school_context_profile"),
        ("schools", "0061_alter_school_governance_help_text"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Employment",
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
                ("title", models.CharField(blank=True, max_length=120)),
                ("started_on", models.DateField()),
                ("ended_on", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="employments",
                        to="governance.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="org_employments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Employment",
                "verbose_name_plural": "Employments",
                "ordering": ("-started_on", "organization__name"),
            },
        ),
        migrations.CreateModel(
            name="SchoolAssignment",
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
                    "role",
                    models.CharField(
                        choices=apps.accounts.models.User.Role.choices,
                        default="TEACHER",
                        max_length=32,
                    ),
                ),
                (
                    "allocation_fraction",
                    models.DecimalField(
                        decimal_places=2,
                        default=1,
                        help_text="1.00 = full-time at this school; 0.50 = half-day cross-campus.",
                        max_digits=4,
                    ),
                ),
                ("started_on", models.DateField()),
                ("ended_on", models.DateField(blank=True, null=True)),
                ("is_primary", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="school_assignments",
                        to="governance.employment",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="org_school_assignments",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "School assignment",
                "verbose_name_plural": "School assignments",
                "ordering": ("-started_on", "school__name"),
            },
        ),
    ]
