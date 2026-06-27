"""Extend GradingScale.scale_type choices to the four international curriculum scales.

The operational ``AssessmentWeights.grading_scale`` already advertised all 15 world
scales (migration 0036), and the registry + durable seed (registries/0008) already
ship UK GCSE 9–1, IB 1–7, German 1–6 and CBSE 10-point. But the per-school
``GradingScale.scale_type`` TextChoices had drifted behind at 9, so a tenant could not
durably SELECT those scales on a ``GradingScale`` row (the choices the wizard /
``ensure_local_grading_scale`` write into). This pure choices-metadata ``AlterField``
brings ``GradingScale.scale_type`` to parity with ``AssessmentWeights.grading_scale``
and the registry — no column/type change, no data migration (the underlying CharField
is unchanged ``max_length=50``).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evals", "0036_alter_assessmentweights_grading_scale"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gradingscale",
            name="scale_type",
            field=models.CharField(
                choices=[
                    ("numeric_0_20", "Numeric 0–20"),
                    ("letter_a_e", "Letters A–E"),
                    ("gpa_4_0", "GPA 4.0"),
                    ("percentage", "Percentage 0–100"),
                    ("numeric_1_5", "Numeric 1–5 (Post-Soviet)"),
                    ("waec_letter", "WAEC letter bands (A1–F9)"),
                    ("pass_fail", "Pass / Fail"),
                    ("qualitative_pd", "Qualitative descriptors"),
                    ("standard_score_t", "T-score (East Asia)"),
                    ("uk_gcse_9_1", "UK GCSE 9–1"),
                    ("ib_1_7", "IB 1–7"),
                    ("german_1_6", "German 1–6"),
                    ("cbse_10", "CBSE 10-point (A1–E2)"),
                    ("french_0_20", "French 0–20"),
                    ("us_letter", "US letter A–F"),
                ],
                default="numeric_0_20",
                max_length=50,
            ),
        ),
    ]
