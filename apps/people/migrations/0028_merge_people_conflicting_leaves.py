# Merge migration to resolve duplicate 0027 leaf nodes in people.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0027_merge_20260212_1854"),
        ("people", "0027_merge_people_rls_and_updated_at"),
    ]

    operations = []
