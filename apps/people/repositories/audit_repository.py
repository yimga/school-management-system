"""
Audit DDL: trigger function, attach/drop triggers, revoke mutations on audit_log.
§2.4 raw_sql_replacement_targets: all audit-related raw SQL for attach_audit_triggers and
revoke_audit_log_permissions lives here; management commands delegate.
PostgreSQL only; staff/operational use.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from django.db import connection

# Unquoted PostgreSQL identifier: max 63 chars; tenant schemas match django-tenants slugs.
_PG_SEARCH_PATH_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Table names embedded (quoted) into CREATE/DROP TRIGGER DDL must be unqualified relnames.
_PG_AUDIT_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Trigger name is "audit_" + table_name; PostgreSQL identifiers are max 63 characters (NAMEDATALEN-1).
_AUDIT_TRIGGER_PREFIX = "audit_"
_MAX_AUDIT_TABLE_NAME_LEN_FOR_TRIGGER = 63 - len(_AUDIT_TRIGGER_PREFIX)

# Each key must be a safe snake_case JSON field name before embedding in ARRAY[...]::text[].
_AUDIT_REDACT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
# Pathological list guard: keep CREATE FUNCTION payload bounded.
_MAX_AUDIT_REDACT_KEYS = 64

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


def _redact_keys_sql_array_literal() -> str:
    """Build ARRAY[...]::text[] for PL/pgSQL; raises ValueError if REDACT_KEYS is malformed, unsafe, or duplicated."""
    try:
        redact_key_count = len(REDACT_KEYS)
    except Exception as exc:
        raise ValueError(
            "REDACT_KEYS must be a finite sized iterable of snake_case strings."
        ) from exc
    if redact_key_count > _MAX_AUDIT_REDACT_KEYS:
        raise ValueError(
            f"REDACT_KEYS must contain at most {_MAX_AUDIT_REDACT_KEYS} entries."
        )
    try:
        redact_keys = iter(REDACT_KEYS)
    except Exception as exc:
        raise ValueError(
            "REDACT_KEYS must be a finite sized iterable of snake_case strings."
        ) from exc
    parts: list[str] = []
    seen_keys: set[str] = set()
    try:
        for k in redact_keys:
            if not isinstance(k, str) or not _AUDIT_REDACT_KEY_RE.fullmatch(k):
                raise ValueError(
                    "REDACT_KEYS entries must be snake_case strings "
                    "(a-z, 0-9, underscore; max 63 characters)."
                )
            if k in seen_keys:
                raise ValueError("REDACT_KEYS must not contain duplicate entries.")
            seen_keys.add(k)
            parts.append(repr(k))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "REDACT_KEYS must be a finite sized iterable of snake_case strings."
        ) from exc
    return "ARRAY[" + ", ".join(parts) + "]::text[]"


def _normalize_identifier(value: str, *, field_name: str) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must not be a boolean.")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(
            f"{field_name} must not be bytes, bytearray, or memoryview."
        )
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise ValueError(f"{field_name} must be a non-blank string.")
    return normalized


def _normalize_unqualified_table_name(table_name: str) -> str:
    if isinstance(table_name, Mapping):
        raise ValueError("table_name must not be a mapping.")
    normalized = _normalize_identifier(table_name, field_name="table_name")
    if "." in normalized:
        raise ValueError("table_name must be unqualified.")
    if not _PG_AUDIT_TABLE_NAME_RE.fullmatch(normalized):
        raise ValueError(
            "table_name must be a single PostgreSQL identifier "
            "(ASCII letters, digits, underscore; max 63 characters)."
        )
    if len(normalized) > _MAX_AUDIT_TABLE_NAME_LEN_FOR_TRIGGER:
        raise ValueError(
            "table_name must be at most 57 characters so the audit trigger identifier "
            "fits the PostgreSQL 63-character limit."
        )
    return normalized


def normalize_search_path_schema_name(schema_name: str) -> str:
    """
    Return a stripped tenant schema name safe for SET LOCAL search_path, or raise ValueError.
    Rejects collections.abc.Mapping, bool, binary buffers, multi-part names, list separators,
    and pathological lengths before raw SQL runs.
    """
    if isinstance(schema_name, Mapping):
        raise ValueError("schema_name must not be a mapping.")
    normalized = _normalize_identifier(schema_name, field_name="schema_name")
    if len(normalized) > 63:
        raise ValueError("schema_name exceeds PostgreSQL identifier length limit.")
    if not _PG_SEARCH_PATH_SCHEMA_RE.fullmatch(normalized):
        raise ValueError(
            "schema_name must be a single unqualified PostgreSQL identifier "
            "(ASCII letters, digits, underscore only)."
        )
    return normalized


def set_search_path(cursor, schema_name: str) -> None:
    """Set search_path for the current transaction. No-op on non-PostgreSQL."""
    if connection.vendor != "postgresql":
        return
    cursor.execute(
        "SET LOCAL search_path TO %s",
        [normalize_search_path_schema_name(schema_name)],
    )


def create_audit_trigger_function(cursor) -> None:
    """
    Create or replace audit_trigger_fn() in the current search_path.

    **Contract:** INSERT must populate every non-auto column on ``TenantAuditLog``
    (``audit_log``): Django uses NOT NULL + no DB default for several fields.
    If you add a non-null field to TenantAuditLog, update this INSERT list.
    See docs/people/AUDIT_LOG_TRIGGER_CONTRACT.md.
    """
    if connection.vendor != "postgresql":
        return
    redact_keys_sql = _redact_keys_sql_array_literal()
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
            new_json := '{}'::jsonb;
            rec_id := (OLD).id::text;
          ELSIF TG_OP = 'UPDATE' THEN
            old_json := to_jsonb(OLD) - redact_keys;
            new_json := to_jsonb(NEW) - redact_keys;
            rec_id := (NEW).id::text;
          ELSE
            old_json := '{}'::jsonb;
            new_json := to_jsonb(NEW) - redact_keys;
            rec_id := (NEW).id::text;
          END IF;
          INSERT INTO audit_log (
            table_name, record_id, action, old_values, new_values, changed_at,
            correlation_id, request_meta, changed_by_id
          )
          VALUES (
            tbl, rec_id, action, old_json, new_json, now(),
            '', '{}'::jsonb, NULL
          );
          IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def drop_audit_trigger(cursor, table_name: str) -> None:
    """Drop the audit trigger for the given table if it exists. Uses quoted identifiers.
    table_name is normalized with _normalize_unqualified_table_name (rejects Mapping; same rules as create_audit_trigger)."""
    if connection.vendor != "postgresql":
        return
    table_name = _normalize_unqualified_table_name(table_name)
    trigger_name = _AUDIT_TRIGGER_PREFIX + table_name.replace(".", "_")
    q_trigger = connection.ops.quote_name(trigger_name)
    q_table = connection.ops.quote_name(table_name)
    cursor.execute("DROP TRIGGER IF EXISTS %s ON %s" % (q_trigger, q_table))


def create_audit_trigger(cursor, table_name: str) -> None:
    """Create AFTER INSERT OR UPDATE OR DELETE trigger for the given table. Uses quoted identifiers.
    table_name is normalized with _normalize_unqualified_table_name (rejects Mapping; same rules as drop_audit_trigger)."""
    if connection.vendor != "postgresql":
        return
    table_name = _normalize_unqualified_table_name(table_name)
    trigger_name = _AUDIT_TRIGGER_PREFIX + table_name.replace(".", "_")
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
