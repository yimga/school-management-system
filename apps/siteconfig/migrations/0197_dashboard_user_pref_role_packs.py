"""Per-user dashboard-pack choice (Dashboard Packs revival, Phase 3)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0196_aiembeddingstore_portable_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboarduserpreference",
            name="role_dashboard_packs",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Per-role dashboard-pack choice (DashboardPack.code). The user may "
                    "only pick among packs their school has installed for that role. "
                    'Example: {"TEACHER": "teacher-planner", "ADMIN": '
                    '"school-admin-operations"}.'
                ),
            ),
        ),
    ]
