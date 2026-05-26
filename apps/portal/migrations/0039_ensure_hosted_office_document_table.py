"""Repair public table drift when 0028 is recorded but portal_hostedofficedocument is absent."""

from django.db import migrations


def _table_names(schema_editor):
    connection = schema_editor.connection
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                """
            )
            return {row[0] for row in cursor.fetchall()}
    return set(connection.introspection.table_names())


def ensure_hosted_office_document_table(apps, schema_editor):
    model = apps.get_model("portal", "HostedOfficeDocument")
    table = model._meta.db_table
    if table in _table_names(schema_editor):
        return
    schema_editor.create_model(model)


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0038_community_forums_1357"),
    ]

    operations = [
        migrations.RunPython(
            ensure_hosted_office_document_table,
            noop_reverse,
        ),
    ]
