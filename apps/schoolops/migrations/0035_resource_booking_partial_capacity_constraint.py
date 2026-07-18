"""Make capacity>1 resources bookable (M10 fix).

The v0029 blanket ExclusionConstraint forbids ANY two overlapping confirmed
bookings for a resource — correct only for capacity=1. Postgres cannot express
"at most N overlapping" for N>1, so this migration:

  1. Drops the blanket constraint (Postgres DB + Django state).
  2. Adds ``ResourceBooking.enforce_exclusive`` (default True) — denormalises the
     capacity=1 case onto the booking row so the DB constraint can be partial.
  3. Backfills it from each row's resource capacity (capacity>1 → False).
  4. Adds a PARTIAL constraint that indexes only ``enforce_exclusive=True`` rows,
     so multi-capacity bookings are no longer blocked by the DB. Capacity for
     capacity>1 is enforced concurrency-safely in
     ``booking_services.create_resource_booking`` under a resource row lock.

ORDER MATTERS on SQLite: adding a NOT-NULL/defaulted column forces SQLite to
REBUILD the table (``_remake_table``), which recreates every constraint in the
model state — and an ``EXCLUDE`` clause is invalid SQLite ("near EXCLUDE: syntax
error"). So the blanket constraint is removed from STATE *before* the AddField,
and the partial constraint is added to STATE *after* it, keeping the SQLite
rebuild free of any exclusion DDL. The exclusion DDL itself is Postgres-only
(vendor-guarded RunPython), mirroring v0029; on other backends only the column +
backfill apply and the table carries no exclusion constraint (as before).

Default True means a row inserted outside the service layer (admin / import /
raw ORM) is still treated as exclusive, preserving the capacity=1 double-booking
backstop.
"""

import django.contrib.postgres.constraints
from django.db import migrations, models

_CONSTRAINT_NAME = "exclude_overlapping_resource_bookings"
_EXPRESSIONS = [
    (models.F("school_id"), "="),
    (models.F("resource_id"), "="),
    (models.F("time_range"), "&&"),
]


def _blanket_constraint():
    return django.contrib.postgres.constraints.ExclusionConstraint(
        name=_CONSTRAINT_NAME,
        expressions=_EXPRESSIONS,
        condition=models.Q(status="confirmed"),
    )


def _partial_constraint():
    return django.contrib.postgres.constraints.ExclusionConstraint(
        name=_CONSTRAINT_NAME,
        expressions=_EXPRESSIONS,
        condition=models.Q(status="confirmed", enforce_exclusive=True),
    )


def _drop_blanket_db(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    ResourceBooking = apps.get_model("schoolops", "ResourceBooking")
    schema_editor.remove_constraint(ResourceBooking, _blanket_constraint())


def _add_blanket_db(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    ResourceBooking = apps.get_model("schoolops", "ResourceBooking")
    schema_editor.add_constraint(ResourceBooking, _blanket_constraint())


def _add_partial_db(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    ResourceBooking = apps.get_model("schoolops", "ResourceBooking")
    schema_editor.add_constraint(ResourceBooking, _partial_constraint())


def _drop_partial_db(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    ResourceBooking = apps.get_model("schoolops", "ResourceBooking")
    schema_editor.remove_constraint(ResourceBooking, _partial_constraint())


def _backfill_enforce_exclusive(apps, schema_editor):
    """capacity>1 bookings are service-enforced, not DB-exclusive."""
    ResourceBooking = apps.get_model("schoolops", "ResourceBooking")
    ResourceBooking.objects.filter(resource__capacity__gt=1).update(
        enforce_exclusive=False
    )
    ResourceBooking.objects.filter(resource__capacity__lte=1).update(
        enforce_exclusive=True
    )


def _noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("schoolops", "0034_inventory_reorder_threshold"),
    ]

    operations = [
        # 1. Remove the blanket constraint from state (and the PG DB) BEFORE the
        #    AddField, so SQLite's table rebuild for the new column does not try
        #    to recreate an EXCLUDE clause it cannot express.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(_drop_blanket_db, _add_blanket_db),
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="resourcebooking",
                    name=_CONSTRAINT_NAME,
                ),
            ],
        ),
        # 2. Real column on every backend.
        migrations.AddField(
            model_name="resourcebooking",
            name="enforce_exclusive",
            field=models.BooleanField(
                default=True,
                db_default=True,
                help_text=(
                    "True when this booking must not overlap any other exclusive "
                    "booking on the same resource — the capacity=1 case, enforced "
                    "by the partial DB exclusion constraint below. Multi-capacity "
                    "(capacity>1) bookings are False: they are excluded from the "
                    "DB overlap index and enforced in the service layer under a "
                    "resource row lock. Defaults True so any row inserted outside "
                    "the service layer is treated as exclusive — failing safe "
                    "against silent double-booking."
                ),
            ),
        ),
        # 3. Backfill from live resource capacity (both backends).
        migrations.RunPython(_backfill_enforce_exclusive, _noop),
        # 4. Add the PARTIAL constraint to state (and the PG DB) AFTER the column
        #    exists and is backfilled.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(_add_partial_db, _drop_partial_db),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="resourcebooking",
                    constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                        name=_CONSTRAINT_NAME,
                        expressions=[
                            (models.F("school_id"), "="),
                            (models.F("resource_id"), "="),
                            (models.F("time_range"), "&&"),
                        ],
                        condition=models.Q(
                            status="confirmed", enforce_exclusive=True
                        ),
                    ),
                ),
            ],
        ),
    ]
