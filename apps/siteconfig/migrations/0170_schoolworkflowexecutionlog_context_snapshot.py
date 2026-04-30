# Generated manually for workflow execution retries

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0169_school_automation_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolworkflowexecutionlog",
            name="context_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Sanitized trigger context for action retries (no secrets).",
            ),
        ),
    ]
