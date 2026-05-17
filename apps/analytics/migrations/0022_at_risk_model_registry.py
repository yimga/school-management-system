"""Wave 1: at-risk ML model registry.

Adds two tables:

  * `analytics_atriskmodelartifact` — single source of truth for which
    artifact is live. Replaces the env-var-only resolution path used
    since Pass 13.D.
  * `analytics_atriskinferencerun` — one row per nightly batch for
    longitudinal drift / capacity questions.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0021_realign_at_risk_outcome_label_indexes"),
        ("schools", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AtRiskModelArtifact",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "model_version",
                    models.CharField(max_length=120, unique=True),
                ),
                ("artifact_path", models.CharField(max_length=512)),
                ("trained_at", models.DateTimeField()),
                (
                    "training_dataset_hash",
                    models.CharField(blank=True, max_length=64),
                ),
                ("training_row_count", models.PositiveIntegerField(default=0)),
                ("feature_order", models.JSONField(default=list)),
                ("metric_roc_auc", models.FloatField(blank=True, null=True)),
                (
                    "metric_average_precision",
                    models.FloatField(blank=True, null=True),
                ),
                ("metric_ece", models.FloatField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("candidate", "Candidate (registered, not in use)"),
                            ("production", "Production (live)"),
                            ("archived", "Archived (previously production)"),
                            ("rejected", "Rejected (failed review)"),
                        ],
                        default="candidate",
                        max_length=20,
                    ),
                ),
                ("registered_at", models.DateTimeField(auto_now_add=True)),
                ("promoted_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "registered_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="at_risk_artifacts_registered",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "promoted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="at_risk_artifacts_promoted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "At-risk model artifact",
                "verbose_name_plural": "At-risk model artifacts",
                "ordering": ["-registered_at"],
            },
        ),
        migrations.AddIndex(
            model_name="atriskmodelartifact",
            index=models.Index(
                fields=["status", "-registered_at"],
                name="analytics_a_status_8a4f12_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="atriskmodelartifact",
            index=models.Index(
                fields=["model_version"],
                name="analytics_a_model_v_1d2e7c_idx",
            ),
        ),
        migrations.CreateModel(
            name="AtRiskInferenceRun",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "model_version_snapshot",
                    models.CharField(blank=True, max_length=120),
                ),
                ("students_scored", models.PositiveIntegerField(default=0)),
                ("students_red_band", models.PositiveIntegerField(default=0)),
                ("students_amber_band", models.PositiveIntegerField(default=0)),
                ("students_green_band", models.PositiveIntegerField(default=0)),
                ("mean_score", models.FloatField(blank=True, null=True)),
                ("median_score", models.FloatField(blank=True, null=True)),
                ("p95_score", models.FloatField(blank=True, null=True)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("ok", "Completed normally"),
                            ("heuristic", "Ran heuristic (no ML model loaded)"),
                            ("partial", "Completed with errors on some schools"),
                            ("failed", "Failed before any scores were written"),
                        ],
                        default="ok",
                        max_length=20,
                    ),
                ),
                ("error_summary", models.TextField(blank=True, default="")),
                (
                    "artifact",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inference_runs",
                        to="analytics.atriskmodelartifact",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="at_risk_inference_runs",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "At-risk inference run",
                "verbose_name_plural": "At-risk inference runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="atriskinferencerun",
            index=models.Index(
                fields=["school", "-started_at"],
                name="analytics_a_school__1f5b2a_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="atriskinferencerun",
            index=models.Index(
                fields=["artifact", "-started_at"],
                name="analytics_a_artifac_3c9e8d_idx",
            ),
        ),
    ]
