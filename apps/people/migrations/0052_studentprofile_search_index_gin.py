# PostgreSQL GIN index on precomputed search_index for FTS performance (Google pillar)

from django.db import migrations


def _add_gin(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE INDEX IF NOT EXISTS people_student_search_index_gin
        ON people_studentprofile
        USING gin (to_tsvector('simple', COALESCE(search_index, '')));
        """
    )


def _drop_gin(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS people_student_search_index_gin;")


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0051_studentprofile_search_index"),
    ]

    operations = [
        migrations.RunPython(_add_gin, _drop_gin),
    ]
