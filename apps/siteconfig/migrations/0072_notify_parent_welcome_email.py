# Phase 2.1: Optional parent welcome email when parent account is created

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('siteconfig', '0071_add_pinned_sidebar_items'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='notify_parent_welcome_email',
            field=models.BooleanField(
                default=False,
                help_text='When a parent account is created (e.g. from backend student create), send a short welcome email. Parent must contact school for login credentials unless you use a separate invite flow.',
            ),
        ),
    ]
