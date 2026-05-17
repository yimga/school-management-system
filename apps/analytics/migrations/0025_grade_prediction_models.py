"""Wave 4: grade-prediction model family.

Three new tables:
  * `analytics_gradepredictionmodelartifact` — registry
  * `analytics_gradepredictionlabel` — operator ground truth
  * `analytics_gradeprediction` — per (student, subject, term) prediction
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0024_riskfactor_feature_contributions"),
        ("academics", "0001_initial"),
        ("people", "0001_initial"),
        ("schools", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GradePredictionModelArtifact",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("model_version", models.CharField(max_length=120, unique=True)),
                ("artifact_path", models.CharField(max_length=512)),
                ("trained_at", models.DateTimeField()),
                ("training_dataset_hash", models.CharField(blank=True, max_length=64)),
                ("training_row_count", models.PositiveIntegerField(default=0)),
                ("feature_order", models.JSONField(default=list)),
                ("metric_mae", models.FloatField(blank=True, null=True)),
                ("metric_rmse", models.FloatField(blank=True, null=True)),
                ("metric_r2", models.FloatField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("candidate", "Candidate"),
                            ("production", "Production"),
                            ("archived", "Archived"),
                            ("rejected", "Rejected"),
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
                        related_name="grade_prediction_artifacts_registered",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "promoted_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grade_prediction_artifacts_promoted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Grade prediction model artifact",
                "verbose_name_plural": "Grade prediction model artifacts",
                "ordering": ["-registered_at"],
            },
        ),
        migrations.AddIndex(
            model_name="gradepredictionmodelartifact",
            index=models.Index(
                fields=["status", "-registered_at"],
                name="analytics_g_status_b9f4c1_idx",
            ),
        ),
        migrations.CreateModel(
            name="GradePredictionLabel",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actual_grade", models.FloatField()),
                ("labeled_at", models.DateTimeField(auto_now=True)),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "academic_year",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grade_prediction_labels",
                        to="academics.academicyear",
                    ),
                ),
                (
                    "labeled_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grade_prediction_labels_set",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_prediction_labels",
                        to="schools.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_prediction_labels",
                        to="people.studentprofile",
                    ),
                ),
                (
                    "subject",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_prediction_labels",
                        to="academics.subject",
                    ),
                ),
                (
                    "term",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grade_prediction_labels",
                        to="academics.term",
                    ),
                ),
            ],
            options={
                "verbose_name": "Grade prediction label",
                "verbose_name_plural": "Grade prediction labels",
                "ordering": ["-labeled_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="gradepredictionlabel",
            constraint=models.UniqueConstraint(
                fields=("student", "subject", "academic_year", "term"),
                name="uniq_grade_pred_label",
            ),
        ),
        migrations.AddIndex(
            model_name="gradepredictionlabel",
            index=models.Index(
                fields=["school", "academic_year", "term"],
                name="analytics_g_school__7d1e22_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="gradepredictionlabel",
            index=models.Index(
                fields=["student"],
                name="analytics_g_student_4a8c93_idx",
            ),
        ),
        migrations.CreateModel(
            name="GradePrediction",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("predicted_grade", models.FloatField()),
                ("confidence_low", models.FloatField(blank=True, null=True)),
                ("confidence_high", models.FloatField(blank=True, null=True)),
                ("reason_summary", models.CharField(blank=True, max_length=500)),
                ("model_version", models.CharField(blank=True, max_length=80)),
                ("feature_contributions", models.JSONField(blank=True, default=list)),
                ("computed_at", models.DateTimeField(auto_now=True)),
                (
                    "academic_year",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grade_predictions",
                        to="academics.academicyear",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_predictions",
                        to="schools.school",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_predictions",
                        to="people.studentprofile",
                    ),
                ),
                (
                    "subject",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grade_predictions",
                        to="academics.subject",
                    ),
                ),
                (
                    "term",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grade_predictions",
                        to="academics.term",
                    ),
                ),
            ],
            options={
                "ordering": ["-computed_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="gradeprediction",
            constraint=models.UniqueConstraint(
                fields=("student", "subject", "academic_year", "term"),
                name="uniq_grade_pred_scope",
            ),
        ),
        migrations.AddIndex(
            model_name="gradeprediction",
            index=models.Index(
                fields=["school", "-computed_at"],
                name="analytics_g_school__c2a8b1_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="gradeprediction",
            index=models.Index(
                fields=["academic_year", "term"],
                name="analytics_g_academ__9e7f54_idx",
            ),
        ),
    ]
