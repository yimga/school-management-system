"""Phase-3 agentic: add `request` + `approval` phases to the audit log.

Destructive (dual-control) actions write a `request` row (party A) and an
`approval` row (party B, distinct) in addition to the shared `outcome` row.
Choices-only change on the existing `phase` field — no data migration.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0081_agentic_audit_phase_reversal"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiagenticactionaudit",
            name="phase",
            field=models.CharField(
                choices=[
                    ("outcome", "Outcome"),
                    ("intent", "Intent"),
                    ("reversal", "Reversal"),
                    ("request", "Request"),
                    ("approval", "Approval"),
                ],
                default="outcome",
                max_length=16,
            ),
        ),
    ]
