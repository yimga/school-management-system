# Plan XVI: Onboarding tours (TourStep) and feature-usage analytics (FeatureUsageEvent)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0019_inventory_transport"),
        ("siteconfig", "0107_user_preference_simple_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TourStep",
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
                    "code",
                    models.CharField(
                        db_index=True,
                        help_text="e.g. dashboard_welcome, grades_first_time",
                        max_length=80,
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tour_steps",
                        to="schools.school",
                    ),
                ),
            ],
            options={"ordering": ["code"]},
        ),
        migrations.CreateModel(
            name="FeatureUsageEvent",
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
                ("feature_code", models.CharField(db_index=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_usage_events",
                        to="schools.school",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="feature_usage_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="featureusageevent",
            index=models.Index(
                fields=["school", "feature_code", "-created_at"],
                name="siteconfig_f_school__feat_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="tourstep",
            constraint=models.UniqueConstraint(
                fields=("school", "code"), name="siteconfig_tourstep_school_code_uniq"
            ),
        ),
    ]
