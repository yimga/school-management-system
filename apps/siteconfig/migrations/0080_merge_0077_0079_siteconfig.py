# Merge migration: resolve conflicting leaves 0077 (syllabus/delegation) and 0079 (heritage report style)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('siteconfig', '0077_add_syllabus_approval_and_delegation_settings'),
        ('siteconfig', '0079_add_heritage_report_style'),
    ]

    operations = [
    ]
