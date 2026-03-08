# Phase 8: Control plane Quick access (pinned sidebar items)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0139_phase4_workflow_dashboard_packs"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboarduserpreference",
            name="control_plane_pinned_items",
            field=models.JSONField(blank=True, default=list, help_text="Control plane sidebar item IDs to show in Quick access."),
        ),
    ]
