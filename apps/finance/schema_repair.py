"""Idempotent finance-table schema repairs (tenant-schema-drift family).

Companion to ``apps/people/schema_repair.py`` and ``apps/schoolops/schema_repair.py``.
Each function is a no-op on a healthy schema and safe to run repeatedly (and
before OR after the declarative migration), so a tenant schema that missed (or
fake-applied) the migration still converges on the next deploy via
``migrate_schemas --tenant``.
"""

from __future__ import annotations

import logging

from django.core.exceptions import FieldDoesNotExist
from django.db import connection

logger = logging.getLogger(__name__)

_OFFLINE_PAYMENT_TABLE = "finance_offlinepaymentintent"
_OFFLINE_PAYMENT_INDEX = "uniq_offlinepaymentintent_invoice_client_id"

_NOTIFICATION_TABLE = "finance_notification"
# Field NAMES (resolved to columns via the live model: ``school`` -> ``school_id``).
_NOTIFICATION_DRIFT_FIELDS = ("dismissed_at", "expires_at", "school")


def ensure_offlinepaymentintent_client_id_index() -> bool:
    """Add the partial-unique index on (invoice_id, client_offline_id) that makes
    offline payment-intent de-duplication ATOMIC.

    ``OfflinePaymentIntent`` shipped with only a plain index on
    ``client_offline_id`` (every sibling offline-capture model got a partial
    unique constraint — this one was missed), so the app-level ``.first()`` dedup
    in ``offline_queue._apply_payment_receipt`` is a non-atomic check-then-create:
    two concurrent offline replays of the SAME captured payment can both pass the
    check and both insert → a duplicate payment intent for one real payment.

    This heals that by:
      1. Conservatively collapsing any EXISTING duplicates — keep the oldest row
         per (invoice_id, client_offline_id) group, blank the key on the rest.
         Non-destructive: no payment row is deleted and reconciliation linkage is
         untouched; the extra rows are simply removed from the dedup scope so the
         unique index can be created and remain visible for manual review.
      2. Creating the partial-unique index ``WHERE client_offline_id <> ''``
         (matches Django's ``UniqueConstraint(condition=~Q(client_offline_id=''))``).

    Idempotent (``CREATE UNIQUE INDEX IF NOT EXISTS``); returns True if it ran.
    """
    with connection.cursor() as cursor:
        if _OFFLINE_PAYMENT_TABLE not in set(
            connection.introspection.table_names(cursor)
        ):
            return False

    q_table = connection.ops.quote_name(_OFFLINE_PAYMENT_TABLE)
    q_index = connection.ops.quote_name(_OFFLINE_PAYMENT_INDEX)

    with connection.cursor() as cursor:
        # 1. Conservative dedupe of pre-existing rows so the unique index can be
        #    created. Keep MIN(id) (oldest) per group; blank the duplicates' key.
        # rls-bypass-allow: schema-repair-dedupe-must-bypass-row-policies-before-unique-index
        cursor.execute(
            f"UPDATE {q_table} SET client_offline_id = '' "
            f"WHERE client_offline_id <> '' AND id NOT IN ("
            f"SELECT MIN(id) FROM {q_table} "
            f"WHERE client_offline_id <> '' GROUP BY invoice_id, client_offline_id"
            f");"
        )
        # 2. Partial-unique index (no-op when it already exists).
        # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-index
        cursor.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {q_index} ON {q_table} "
            "(invoice_id, client_offline_id) WHERE client_offline_id <> '';"
        )
    return True


def ensure_finance_notification_columns() -> bool:
    """Add ``dismissed_at`` / ``expires_at`` / ``school_id`` to ``finance_notification``.

    Heals the drift class where finance ``0071`` is recorded as applied but its
    ``AddField`` never physically landed in a tenant schema, so
    ``/api/notifications/unread_count/`` (and therefore the notification bell on
    EVERY authenticated page) 500s with
    ``column finance_notification.dismissed_at does not exist``.

    Each missing field is resolved from the LIVE model so the column type / null /
    FK definition exactly matches the migration, then added via the schema editor.
    Idempotent: introspects the live columns first and skips any that already
    exist; a no-op (one introspection) on a healthy schema. Returns True if it
    added at least one column.
    """
    from apps.finance.models import Notification

    table = Notification._meta.db_table
    with connection.cursor() as cursor:
        if table not in set(connection.introspection.table_names(cursor)):
            return False
        existing = {
            col.name
            for col in connection.introspection.get_table_description(cursor, table)
        }

    changed = False
    for field_name in _NOTIFICATION_DRIFT_FIELDS:
        try:
            field = Notification._meta.get_field(field_name)
        except FieldDoesNotExist:
            continue
        if field.column in existing:
            continue
        # rls-bypass-allow: schema-repair-ddl-must-bypass-row-policies-to-add-column
        with connection.schema_editor() as editor:
            editor.add_field(Notification, field)
        existing.add(field.column)
        changed = True
        logger.warning(
            "finance schema_repair: added missing column %s.%s", table, field.column
        )
    return changed


def ensure_finance_schema_current() -> bool:
    """Run every idempotent finance-table schema repair. Returns True if any ran."""
    ran_index = ensure_offlinepaymentintent_client_id_index()
    ran_notif = ensure_finance_notification_columns()
    return bool(ran_index or ran_notif)
