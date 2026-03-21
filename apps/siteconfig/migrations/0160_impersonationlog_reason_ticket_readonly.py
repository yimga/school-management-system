# Generated manually for operator impersonation audit fields.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0159_add_workflow_dashboard_recommended_sectors"),
    ]

    operations = [
        migrations.AddField(
            model_name="impersonationlog",
            name="reason",
            field=models.TextField(
                blank=True,
                help_text="Operator justification for impersonation (governance / audit).",
            ),
        ),
        migrations.AddField(
            model_name="impersonationlog",
            name="support_ticket_ref",
            field=models.CharField(
                blank=True,
                help_text="External ticket or incident reference, if any.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="impersonationlog",
            name="read_only",
            field=models.BooleanField(
                blank=True,
                help_text="Whether the impersonation session was read-only (None = legacy log rows).",
                null=True,
            ),
        ),
    ]
