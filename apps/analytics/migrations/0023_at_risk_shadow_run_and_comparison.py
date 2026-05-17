"""Wave 2: at-risk shadow comparison (production vs candidate).

Adds two tables:
  * `analytics_atriskshadowrun` — aggregate per shadow batch
  * `analytics_atriskshadowcomparison` — per-student prod-vs-candidate row
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0022_at_risk_model_registry"),
        ("people", "0001_initial"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AtRiskShadowRun",
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
                ("students_scored", models.PositiveIntegerField(default=0)),
                ("band_changes", models.PositiveIntegerField(default=0)),
                ("promotions", models.PositiveIntegerField(default=0)),
                ("demotions", models.PositiveIntegerField(default=0)),
                ("agreement_pct", models.FloatField(blank=True, null=True)),
                ("mean_abs_delta", models.FloatField(blank=True, null=True)),
                ("median_abs_delta", models.FloatField(blank=True, null=True)),
                ("p95_abs_delta", models.FloatField(blank=True, null=True)),
                (
                    "psi_score_distribution",
                    models.FloatField(blank=True, null=True),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("ok", "Completed normally"),
                            ("skipped", "No candidate or no production to compare"),
                            ("failed", "Aborted with error"),
                        ],
                        default="ok",
                        max_length=20,
                    ),
                ),
                ("error_summary", models.TextField(blank=True, default="")),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="at_risk_shadow_runs",
                        to="schools.school",
                    ),
                ),
                (
                    "production_artifact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="shadow_runs_as_production",
                        to="analytics.atriskmodelartifact",
                    ),
                ),
                (
                    "candidate_artifact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="shadow_runs_as_candidate",
                        to="analytics.atriskmodelartifact",
                    ),
                ),
            ],
            options={
                "verbose_name": "At-risk shadow run",
                "verbose_name_plural": "At-risk shadow runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="atriskshadowrun",
            index=models.Index(
                fields=["school", "-started_at"],
                name="analytics_a_school__3e7a91_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="atriskshadowrun",
            index=models.Index(
                fields=["candidate_artifact", "-started_at"],
                name="analytics_a_candida_5b1f44_idx",
            ),
        ),
        migrations.CreateModel(
            name="AtRiskShadowComparison",
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
                ("production_score", models.FloatField()),
                ("candidate_score", models.FloatField()),
                ("score_delta", models.FloatField()),
                ("production_band", models.CharField(max_length=10)),
                ("candidate_band", models.CharField(max_length=10)),
                ("band_changed", models.BooleanField(default=False)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comparisons",
                        to="analytics.atriskshadowrun",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="at_risk_shadow_comparisons",
                        to="people.studentprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "At-risk shadow comparison",
                "verbose_name_plural": "At-risk shadow comparisons",
            },
        ),
        migrations.AddIndex(
            model_name="atriskshadowcomparison",
            index=models.Index(
                fields=["run", "-score_delta"],
                name="analytics_a_run_id_4a2c8e_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="atriskshadowcomparison",
            index=models.Index(
                fields=["run", "band_changed"],
                name="analytics_a_run_id_band_7d5f10_idx",
            ),
        ),
    ]
