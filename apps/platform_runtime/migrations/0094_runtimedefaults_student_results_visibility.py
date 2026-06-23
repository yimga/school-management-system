# Per-tenant student dashboard grade visibility (off / published / entered).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0093_runtimedefaults_mfa_enforcement"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimedefaults",
            name="student_results_visibility",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=16,
                choices=[
                    ("off", "Hidden from student dashboard"),
                    ("published", "Published term results only (default)"),
                    ("entered", "Show entered marks as teachers save them"),
                ],
                help_text=(
                    "Governance for grade/result panels on the student role home. "
                    "Blank/None = published-only (legacy-safe default). Resolved by "
                    "apps.portal.student_results_visibility."
                ),
            ),
        ),
    ]
