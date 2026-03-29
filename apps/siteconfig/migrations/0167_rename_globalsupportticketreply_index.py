# Align GlobalSupportTicketReply (ticket, created_at) index name with Django 5.2 default.
# RenameIndex alone fails on gate SQLite DBs that applied an older 0165 revision without AddIndex.

from django.db import migrations
from django.db.migrations.operations.special import SeparateDatabaseAndState


def _fix_globalsupportticketreply_ticket_created_index(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor
    table = "siteconfig_globalsupportticketreply"
    old_name = "siteconfig_gstreply_tc"
    new_name = "siteconfig__ticket__cc7d04_idx"
    qn = schema_editor.quote_name

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table)
    has_old = old_name in constraints
    has_new = new_name in constraints
    if has_new:
        return

    with connection.cursor() as cursor:
        if has_old:
            if vendor == "postgresql":
                cursor.execute(
                    f"ALTER INDEX {qn(old_name)} RENAME TO {qn(new_name)}"
                )
            elif vendor == "sqlite":
                # SQLite (incl. test DBs): no portable ALTER INDEX RENAME — rebuild index.
                cursor.execute(f"DROP INDEX {qn(old_name)}")
                cursor.execute(
                    f"CREATE INDEX {qn(new_name)} ON {qn(table)} "
                    f"({qn('ticket_id')}, {qn('created_at')})"
                )
            else:
                cursor.execute(
                    f"DROP INDEX {qn(old_name)} ON {qn(table)}"
                )
                cursor.execute(
                    f"CREATE INDEX {qn(new_name)} ON {qn(table)} "
                    f"({qn('ticket_id')}, {qn('created_at')})"
                )
        else:
            cursor.execute(
                f"CREATE INDEX {qn(new_name)} ON {qn(table)} "
                f"({qn('ticket_id')}, {qn('created_at')})"
            )


def _reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0166_globalsupportticketwebhookendpoint"),
    ]

    operations = [
        SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    _fix_globalsupportticketreply_ticket_created_index,
                    _reverse_noop,
                ),
            ],
            state_operations=[
                migrations.RenameIndex(
                    model_name="globalsupportticketreply",
                    new_name="siteconfig__ticket__cc7d04_idx",
                    old_name="siteconfig_gstreply_tc",
                ),
            ],
        ),
    ]
