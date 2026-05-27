"""Repair table drift when 0028 is recorded but portal_hostedofficedocument is absent.

Must introspect the active schema (public or tenant), not public only — otherwise
tenant migrate_schemas attempts CREATE on an existing portal_hostedofficedocument.
"""

from django.db import migrations


def _schema_name(connection):
    return getattr(connection, "schema_name", None) or "public"


def _table_exists(schema_editor, schema_name, table_name):
    connection = schema_editor.connection
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                """,
                [schema_name, table_name],
            )
            return cursor.fetchone() is not None
    return table_name in set(connection.introspection.table_names())


def ensure_hosted_office_document_table(apps, schema_editor):
    model = apps.get_model("portal", "HostedOfficeDocument")
    table = model._meta.db_table
    schema = _schema_name(schema_editor.connection)
    if _table_exists(schema_editor, schema, table):
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
