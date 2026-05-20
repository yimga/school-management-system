from django.db import migrations


def _ensure_column(apps, schema_editor):
    from apps.people.schema_repair import ensure_teacherprofile_updated_at_column

    ensure_teacherprofile_updated_at_column()


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0052_studentprofile_search_index_gin"),
    ]

    operations = [
        migrations.RunPython(_ensure_column, migrations.RunPython.noop),
    ]
