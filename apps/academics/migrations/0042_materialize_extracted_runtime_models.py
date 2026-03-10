from django.conf import settings
from django.db import migrations


def _schema_name(connection):
    return getattr(connection, "schema_name", None) or "public"


def _table_exists(schema_editor, schema_name, table_name):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            [schema_name, table_name],
        )
        return cursor.fetchone() is not None


def _qualified(schema_editor, schema_name, table_name):
    quote_name = schema_editor.connection.ops.quote_name
    return f"{quote_name(schema_name)}.{quote_name(table_name)}"


def _column_names(model):
    return [field.column for field in model._meta.local_concrete_fields]


def _ensure_model_table(apps, schema_editor, model_name):
    model = apps.get_model("academics", model_name)
    current_schema = _schema_name(schema_editor.connection)
    if not _table_exists(schema_editor, current_schema, model._meta.db_table):
        schema_editor.create_model(model)
    return model


def _current_school_id(apps, schema_editor):
    Client = apps.get_model("customers", "Client")
    client = Client.objects.filter(schema_name=_schema_name(schema_editor.connection)).only("school_id").first()
    return getattr(client, "school_id", None)


def _copy_rows(schema_editor, model, where_sql="", params=None):
    current_schema = _schema_name(schema_editor.connection)
    params = params or []
    if not _table_exists(schema_editor, "public", model._meta.db_table):
        return
    if not _table_exists(schema_editor, current_schema, model._meta.db_table):
        return
    columns = _column_names(model)
    quoted_columns = ", ".join(schema_editor.connection.ops.quote_name(column) for column in columns)
    sql = (
        f"INSERT INTO {_qualified(schema_editor, current_schema, model._meta.db_table)} ({quoted_columns}) "
        f"SELECT {quoted_columns} FROM {_qualified(schema_editor, 'public', model._meta.db_table)}"
    )
    if where_sql:
        sql += f" WHERE {where_sql}"
    sql += ' ON CONFLICT ("id") DO NOTHING'
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql, params)


def materialize_extracted_runtime_models(apps, schema_editor):
    if not getattr(settings, "USE_DJANGO_TENANTS", False):
        return
    current_schema = _schema_name(schema_editor.connection)
    if current_schema == "public":
        return
    school_id = _current_school_id(apps, schema_editor)
    if not school_id:
        return

    create_order = [
        "ReportCardStyleAssignment",
        "RolloverProposal",
        "RolloverProposalItem",
        "HolidayCalendar",
    ]
    models_by_name = {
        model_name: _ensure_model_table(apps, schema_editor, model_name)
        for model_name in create_order
    }

    _copy_rows(schema_editor, models_by_name["RolloverProposal"], "school_id = %s", [school_id])

    public_rollover = _qualified(schema_editor, "public", "accounts_rolloverproposal")
    _copy_rows(
        schema_editor,
        models_by_name["RolloverProposalItem"],
        f"proposal_id IN (SELECT id FROM {public_rollover} WHERE school_id = %s)",
        [school_id],
    )

    current_classrooms = _qualified(schema_editor, current_schema, "academics_classroom")
    _copy_rows(
        schema_editor,
        models_by_name["ReportCardStyleAssignment"],
        f"classroom_id IN (SELECT id FROM {current_classrooms})",
    )

    current_years = _qualified(schema_editor, current_schema, "academics_academicyear")
    _copy_rows(
        schema_editor,
        models_by_name["HolidayCalendar"],
        f"academic_year_id IN (SELECT id FROM {current_years})",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0041_reportcardstyleassignment_rolloverproposal_and_more"),
    ]

    operations = [
        migrations.RunPython(materialize_extracted_runtime_models, migrations.RunPython.noop),
    ]
