"""Idempotent finance-table schema repairs (tenant-schema-drift family).

Companion to ``apps/people/schema_repair.py`` and ``apps/schoolops/schema_repair.py``.
Each function is a no-op on a healthy schema and safe to run repeatedly (and
before OR after the declarative migration), so a tenant schema that missed (or
fake-applied) the migration still converges on the next deploy via
``migrate_schemas --tenant``.
"""

from __future__ import annotations

import logging

from django.db import connection

logger = logging.getLogger(__name__)

_OFFLINE_PAYMENT_TABLE = "finance_offlinepaymentintent"
_OFFLINE_PAYMENT_INDEX = "uniq_offlinepaymentintent_invoice_client_id"


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


def ensure_finance_schema_current() -> bool:
    """Run every idempotent finance-table schema repair. Returns True if any ran."""
    return bool(ensure_offlinepaymentintent_client_id_index())
