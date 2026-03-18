# Optional: enable PGVector extension on PostgreSQL for future vector similarity search.
# Requires pgvector to be installed on the Postgres server (e.g. apt install postgresql-16-pgvector).
# No-op on SQLite and other backends.

from django.db import migrations


def enable_pgvector(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0122_regionalaiconfig_preferred_model_id"),
    ]

    operations = [
        migrations.RunPython(enable_pgvector, noop),
    ]
