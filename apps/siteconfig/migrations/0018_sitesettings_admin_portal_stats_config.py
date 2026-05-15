from django.db import migrations, models


def default_admin_portal_stats_config():
    """Inlined from ``apps.siteconfig.models.default_admin_portal_stats_config``
    for migration historical-state safety.
    """
    return {
        "sections": ["academics", "accounts", "finance"],
        "max_sections": 3,
        "max_items": 3,
        "items": {
            "academics": ["Students", "Classrooms", "Subjects"],
            "accounts": ["Users", "Teachers", "Guardians"],
            "finance": ["Invoices", "Overdue", "Draft"],
        },
    }


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0016_alter_userpreference_timezone"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="admin_portal_stats_config",
            field=models.JSONField(
                blank=True,
                default=default_admin_portal_stats_config,
                help_text=(
                    "Admin portal stats JSON. Keys: sections, max_sections, max_items, items. "
                    'Example: {"sections":["academics"],"max_items":2,"items":{"academics":["Students"]}}'
                ),
            ),
        ),
    ]
