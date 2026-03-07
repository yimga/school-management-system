# Idempotent: ensure vat_rate and report_currency_code exist on complianceprofile (Render tenant schemas).

from decimal import Decimal

from django.db import migrations


def _column_exists_pg(cursor, table, column):
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return cursor.fetchone() is not None


def _column_exists_sqlite(cursor, table, column):
    cursor.execute("PRAGMA table_info(%s)" % table)
    return any(row[1] == column for row in cursor.fetchall())


def add_columns_if_missing(apps, schema_editor):
    conn = schema_editor.connection
    table = "finance_complianceprofile"
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            if not _column_exists_pg(cursor, table, "report_currency_code"):
                cursor.execute(
                    "ALTER TABLE finance_complianceprofile ADD COLUMN report_currency_code varchar(3) NOT NULL DEFAULT ''"
                )
            if not _column_exists_pg(cursor, table, "vat_rate"):
                cursor.execute(
                    "ALTER TABLE finance_complianceprofile ADD COLUMN vat_rate decimal(6,2) NOT NULL DEFAULT 0.00"
                )
        else:
            if not _column_exists_sqlite(cursor, table, "report_currency_code"):
                cursor.execute(
                    "ALTER TABLE finance_complianceprofile ADD COLUMN report_currency_code varchar(3) NOT NULL DEFAULT ''"
                )
            if not _column_exists_sqlite(cursor, table, "vat_rate"):
                cursor.execute(
                    "ALTER TABLE finance_complianceprofile ADD COLUMN vat_rate decimal(6,2) NOT NULL DEFAULT 0.00"
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0045_remove_recurringpaymentsubscription_plan_and_more"),
    ]

    operations = [
        migrations.RunPython(add_columns_if_missing, noop),
    ]
