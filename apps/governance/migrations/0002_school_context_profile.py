# Global governance Phase 3C — multi-role context profiles.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("governance", "0001_initial"),
        ("schools", "0062_school_institution_type_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolContextProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        default="ADMIN",
                        max_length=20,
                    ),
                ),
                (
                    "context_key",
                    models.SlugField(
                        help_text="Stable slug for this persona (e.g. teacher, student, parent).",
                        max_length=64,
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        help_text="Human label shown in the context switcher.",
                        max_length=120,
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text="Preferred profile when the user lands on this school.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="context_profiles",
                        to="schools.school",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="school_context_profiles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "School context profile",
                "verbose_name_plural": "School context profiles",
                "ordering": ("-is_default", "school__name", "label"),
                "unique_together": {("user", "school", "context_key")},
            },
        ),
    ]
