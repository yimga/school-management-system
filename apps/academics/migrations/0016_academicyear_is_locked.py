# Generated manually for year-end lock

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0015_certificationexamsession_admin_overrides'),
    ]

    operations = [
        migrations.AddField(
            model_name='academicyear',
            name='is_locked',
            field=models.BooleanField(
                default=False,
                help_text='When set, no further grade edits or rollover from this year (year-end lock).',
            ),
        ),
    ]
