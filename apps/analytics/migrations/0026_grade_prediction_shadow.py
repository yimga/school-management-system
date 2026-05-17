"""Wave 7: shadow comparison tables for grade-prediction family."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0025_grade_prediction_models"),
        ("academics", "0001_initial"),
        ("people", "0001_initial"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GradePredictionShadowRun",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("rows_compared", models.PositiveIntegerField(default=0)),
                ("mean_abs_delta", models.FloatField(blank=True, null=True)),
                ("median_abs_delta", models.FloatField(blank=True, null=True)),
                ("p95_abs_delta", models.FloatField(blank=True, null=True)),
                ("bias", models.FloatField(blank=True, null=True)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("ok", "Completed normally"),
                            ("skipped", "No candidate or no production"),
                            ("failed", "Aborted with error"),
                        ],
                        default="ok", max_length=20,
                    ),
                ),
                ("error_summary", models.TextField(blank=True, default="")),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_pred_shadow_runs",
                        to="schools.school",
                    ),
                ),
                (
                    "production_artifact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grade_shadow_runs_as_production",
                        to="analytics.gradepredictionmodelartifact",
                    ),
                ),
                (
                    "candidate_artifact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grade_shadow_runs_as_candidate",
                        to="analytics.gradepredictionmodelartifact",
                    ),
                ),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.AddIndex(
            model_name="gradepredictionshadowrun",
            index=models.Index(
                fields=["school", "-started_at"],
                name="analytics_g_school__d3a8f2_idx",
            ),
        ),
        migrations.CreateModel(
            name="GradePredictionShadowComparison",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("production_grade", models.FloatField()),
                ("candidate_grade", models.FloatField()),
                ("grade_delta", models.FloatField()),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comparisons",
                        to="analytics.gradepredictionshadowrun",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_pred_shadow_comparisons",
                        to="people.studentprofile",
                    ),
                ),
                (
                    "subject",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_pred_shadow_comparisons",
                        to="academics.subject",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="gradepredictionshadowcomparison",
            index=models.Index(
                fields=["run", "-grade_delta"],
                name="analytics_g_run_id__8e2c91_idx",
            ),
        ),
    ]
