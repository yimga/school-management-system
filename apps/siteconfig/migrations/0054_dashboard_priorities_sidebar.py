# Generated manually for dashboard priorities right sidebar (configurable from Admin)

from django.db import migrations, models


def default_dashboard_priorities_sidebar():
    return {
        "enabled_parent": True,
        "enabled_teacher": True,
        "title": "My priorities",
        "max_items_per_section": 5,
        "sections": {
            "grading_deadlines": {"enabled": True, "label": "Grading deadlines", "roles": ["TEACHER"]},
            "upcoming_events": {"enabled": True, "label": "Upcoming events", "roles": ["PARENT", "TEACHER"]},
            "upcoming_meetings": {"enabled": True, "label": "Upcoming meetings", "roles": ["PARENT", "TEACHER"]},
            "fee_reminders": {"enabled": True, "label": "Fee reminders", "roles": ["PARENT"]},
        },
    }


class Migration(migrations.Migration):

    dependencies = [
        ('siteconfig', '0053_alter_sitesettings_default_dashboard_view_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='dashboard_priorities_sidebar',
            field=models.JSONField(
                blank=True,
                default=default_dashboard_priorities_sidebar,
                help_text=(
                    "Right sidebar on parent/teacher dashboards: enabled_parent, enabled_teacher, title, "
                    "max_items_per_section, sections (grading_deadlines, upcoming_events, upcoming_meetings, "
                    "fee_reminders) with enabled, label, roles."
                ),
            ),
        ),
    ]
