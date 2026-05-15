"""Wave O4 — at-risk outcome label model for retrospective training data."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0019_alter_gradeimportjob_uploaded_file"),
        ("academics", "0048_classroom_settings_lexicon_k1"),
        ("people", "0001_initial"),
        ("schools", "0049_school_data_region_g4"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AtRiskOutcomeLabel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("label", models.CharField(
                    choices=[
                        ("at_risk", "At-risk (outcome confirmed)"),
                        ("not_at_risk", "Not at-risk (false positive / clean term)"),
                        ("recovered", "Recovered after intervention"),
                        ("unknown", "Unknown / insufficient data"),
                    ],
                    max_length=20,
                )),
                ("labeled_at", models.DateTimeField(auto_now=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("school", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="at_risk_outcome_labels",
                    to="schools.school",
                )),
                ("student", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="at_risk_outcome_labels",
                    to="people.studentprofile",
                )),
                ("academic_year", models.ForeignKey(
                    on_delete=models.deletion.PROTECT,
                    related_name="at_risk_outcome_labels",
                    to="academics.academicyear",
                )),
                ("labeled_by", models.ForeignKey(
                    on_delete=models.deletion.PROTECT,
                    related_name="at_risk_labels_set",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "At-risk outcome label",
                "verbose_name_plural": "At-risk outcome labels",
                "ordering": ["-labeled_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="atriskoutcomelabel",
            constraint=models.UniqueConstraint(
                fields=("student", "academic_year"),
                name="uniq_at_risk_outcome_student_year",
            ),
        ),
        migrations.AddIndex(
            model_name="atriskoutcomelabel",
            index=models.Index(fields=["school", "academic_year"], name="analytics_a_school__b66ad6_idx"),
        ),
        migrations.AddIndex(
            model_name="atriskoutcomelabel",
            index=models.Index(fields=["label"], name="analytics_a_label_e07e35_idx"),
        ),
    ]
