"""Phase-2 agentic: add `phase` + `reversal_payload` to the agentic audit log.

`phase` distinguishes the intent row (written BEFORE a mutating runner) from the
outcome row (after); `reversal_payload` carries pseudonymous record refs needed to
undo a reversible action. Read-only Phase-1 rows keep phase=outcome (the default).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_runtime", "0080_ai_agentic_action_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiagenticactionaudit",
            name="phase",
            field=models.CharField(
                choices=[
                    ("outcome", "Outcome"),
                    ("intent", "Intent"),
                    ("reversal", "Reversal"),
                ],
                default="outcome",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="aiagenticactionaudit",
            name="reversal_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="aiagenticactionaudit",
            name="audit_id",
            field=models.CharField(db_index=True, max_length=32),
        ),
        migrations.AlterField(
            model_name="aiagenticactionaudit",
            name="outcome",
            field=models.CharField(
                choices=[
                    ("ok", "Ok"),
                    ("blocked", "Blocked"),
                    ("error", "Error"),
                    ("pending", "Pending"),
                    ("reversed", "Reversed"),
                ],
                default="ok",
                max_length=16,
            ),
        ),
    ]
