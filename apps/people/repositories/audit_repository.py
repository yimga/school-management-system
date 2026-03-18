"""
Audit DDL: trigger function, attach/drop triggers, revoke mutations on audit_log.
§2.4 raw_sql_replacement_targets: all audit-related raw SQL for attach_audit_triggers and
revoke_audit_log_permissions lives here; management commands delegate.
PostgreSQL only; staff/operational use.
"""

from __future__ import annotations

from django.db import connection

# Must match migration 0037 REDACT_KEYS (PII masking).
REDACT_KEYS = [
    "password",
    "password_hash",
    "secret",
    "token",
    "api_key",
    "card_last4",
    "card_number",
    "ssn",
    "social_security",
]


def set_search_path(cursor, schema_name: str) -> None:
    """Set search_path for the current session. No-op on non-PostgreSQL."""
    if connection.vendor != "postgresql":
        return
    cursor.execute("SET search_path TO %s", [schema_name])


def create_audit_trigger_function(cursor) -> None:
    """Create or replace audit_trigger_fn() in the current search_path."""
    if connection.vendor != "postgresql":
        return
    redact_keys_sql = "ARRAY[" + ", ".join(repr(k) for k in REDACT_KEYS) + "]::text[]"
    cursor.execute(
        """
        CREATE OR REPLACE FUNCTION audit_trigger_fn()
        RETURNS TRIGGER AS $$
        DECLARE
          old_json jsonb;
          new_json jsonb;
          action text;
          tbl text;
          rec_id text;
          redact_keys text[] := """
        + redact_keys_sql
        + """;
        BEGIN
          tbl := TG_TABLE_NAME;
          action := TG_OP;
          IF TG_OP = 'DELETE' THEN
            old_json := to_jsonb(OLD) - redact_keys;
            new_json := NULL;
            rec_id := (OLD).id::text;
          ELSIF TG_OP = 'UPDATE' THEN
            old_json := to_jsonb(OLD) - redact_keys;
            new_json := to_jsonb(NEW) - redact_keys;
            rec_id := (NEW).id::text;
          ELSE
            -- INSERT: audit_log.old_values is NOT NULL; empty object = no prior row
            old_json := '{}'::jsonb;
            new_json := to_jsonb(NEW) - redact_keys;
            rec_id := (NEW).id::text;
          END IF;
          INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, changed_at)
          VALUES (tbl, rec_id, action, old_json, new_json, now());
          IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def drop_audit_trigger(cursor, table_name: str) -> None:
    """Drop the audit trigger for the given table if it exists. Uses quoted identifiers."""
    if connection.vendor != "postgresql":
        return
    trigger_name = "audit_" + table_name.replace(".", "_")
    q_trigger = connection.ops.quote_name(trigger_name)
    q_table = connection.ops.quote_name(table_name)
    cursor.execute("DROP TRIGGER IF EXISTS %s ON %s" % (q_trigger, q_table))


def create_audit_trigger(cursor, table_name: str) -> None:
    """Create AFTER INSERT OR UPDATE OR DELETE trigger for the given table. Uses quoted identifiers."""
    if connection.vendor != "postgresql":
        return
    trigger_name = "audit_" + table_name.replace(".", "_")
    q_trigger = connection.ops.quote_name(trigger_name)
    q_table = connection.ops.quote_name(table_name)
    cursor.execute(
        "CREATE TRIGGER %s AFTER INSERT OR UPDATE OR DELETE ON %s "
        "FOR EACH ROW EXECUTE PROCEDURE audit_trigger_fn()" % (q_trigger, q_table)
    )


def revoke_audit_log_mutations(cursor) -> None:
    """Revoke UPDATE and DELETE on audit_log from CURRENT_USER (immutable audit trail)."""
    if connection.vendor != "postgresql":
        return
    cursor.execute("REVOKE UPDATE, DELETE ON audit_log FROM CURRENT_USER;")
