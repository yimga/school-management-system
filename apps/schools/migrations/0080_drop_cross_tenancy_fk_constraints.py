"""Drop the four SHARED -> TENANT foreign-key CONSTRAINTS that cannot exist.

``apps.schools`` is a SHARED app (it lives in ``public``); ``apps.finance`` and
``apps.schoolops`` are TENANT apps (one copy per tenant schema). Under
``USE_DJANGO_TENANTS=1`` — what ``render.yaml`` sets — a ``public`` table simply
cannot carry a REFERENCES clause to a tenant table: the target does not exist in
``public``, and there are N copies of it, so the constraint has no single
referent even in principle.

Four fields had been generated with a real DB constraint anyway, which made
``migrate_schemas --shared`` (``scripts/release/render_predeploy.sh:47``) die on
any FRESH database with ``relation "finance_awardsource" does not exist`` —
breaking DR restore, a new region, a staging rebuild and every preview env.
Twelve OTHER cross-boundary FKs in this codebase already carried
``db_constraint=False``; these four were the outliers.

The fields keep their ForeignKey (the ORM relation is still useful inside tenant
context, where ``search_path`` spans both schemas) and gain
``db_constraint=False``. The historical migrations that created them were
amended in place so a fresh replay never emits the constraint at all. This
migration closes the other half: an EXISTING database already ran those
migrations, so it still carries the constraints — here we drop them, and the two
kinds of database converge on the same schema.

Constraint names are auto-generated hashes, so we introspect rather than guess.
Non-PostgreSQL backends (the SQLite test suites) have no such constraints to
drop and are a deliberate no-op.
"""
from __future__ import annotations

from django.db import DatabaseError, migrations, transaction

# (table, column) pairs whose FK constraint must not exist.
_CROSS_TENANCY_COLUMNS = [
    ("schools_advancementgift", "award_source_id"),
    ("schools_inkinddonation", "inventory_item_id"),
    ("schools_fundraisingcampaign", "award_source_id"),
    ("schools_grantapplication", "award_source_id"),
]


def _drop_foreign_key_constraints(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    for table, column in _CROSS_TENANCY_COLUMNS:
        # Each table gets its OWN savepoint. A migration runs inside a
        # transaction, and on Postgres one failed statement aborts all of it —
        # so introspecting a table that isn't there would take the whole
        # migration down with it rather than being skipped. (This is the same
        # class of bug as ``apps/schools/db_safety.py``; that helper is not
        # importable here because a migration must not import app code.)
        try:
            with transaction.atomic(using=connection.alias):
                with connection.cursor() as cursor:
                    constraints = connection.introspection.get_constraints(cursor, table)
                    for name, details in constraints.items():
                        if not details.get("foreign_key"):
                            continue
                        if list(details.get("columns") or []) != [column]:
                            continue
                        cursor.execute(
                            'ALTER TABLE "%s" DROP CONSTRAINT IF EXISTS "%s"'
                            % (table, name)
                        )
        except DatabaseError:
            # Absent table (a schema that never had it) — nothing to drop, and
            # the savepoint has already rolled the failure back.
            continue


class Migration(migrations.Migration):
    """Database-only: the model state already says ``db_constraint=False``."""

    dependencies = [
        ("schools", "0079_retire_gilead_school_husk"),
    ]

    operations = [
        migrations.RunPython(
            _drop_foreign_key_constraints,
            migrations.RunPython.noop,
        ),
    ]
