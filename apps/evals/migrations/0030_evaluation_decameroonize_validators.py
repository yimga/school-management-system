"""Pass 8.D (2026-05-11): drop hardcoded `MaxValueValidator(20)` on Evaluation
score fields. The 0-20 cap is Cameroon-specific; global schools declare their
max via the GradingScale bound to their region (US 0-100, UK 0-100,
Cameroon 0-20, IB 0-7, etc.). Forms and views resolve the per-tenant max;
the model only enforces the lower bound (>= 0) and the column width.

This migration is a no-op at the DB level — Django validators are
form/clean-time only, not column constraints. Recording it explicitly keeps
the migration graph aligned with model changes for schema diff tooling.
"""

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evals", "0029_grading_scale_bands"),
    ]

    operations = [
        migrations.AlterField(
            model_name="evaluation",
            name="seq1_score",
            field=models.DecimalField(
                "Seq 1",
                max_digits=5,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="evaluation",
            name="seq2_score",
            field=models.DecimalField(
                "Seq 2",
                max_digits=5,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="evaluation",
            name="exam_score",
            field=models.DecimalField(
                "Exam",
                max_digits=5,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="evaluation",
            name="mock_score",
            field=models.DecimalField(
                "Mock",
                max_digits=5,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="evaluation",
            name="practical_score",
            field=models.DecimalField(
                "Practical",
                max_digits=5,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="evaluation",
            name="internship_score",
            field=models.DecimalField(
                "Industrial attachment / Internship",
                max_digits=5,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[MinValueValidator(0)],
                help_text=(
                    "Industrial attachment (Paper 3) or internship mark; "
                    "may sync to sequence."
                ),
            ),
        ),
    ]
