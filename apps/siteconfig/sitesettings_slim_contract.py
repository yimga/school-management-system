"""
Invariant: after Phase B Batch 0 (0162), the siteconfig tenant settings singleton is a slim DB row.

Only these local concrete columns may exist on that singleton:
``id``, ``maintenance_mode``, ``updated_at``. All other product keys are virtual
(``__getattr__`` -> ``RuntimeDefaults.payload`` / snapshots / PGB) or properties.

Enforced by ``scripts/verify_phase_b_execution.py`` (pre-deploy) and
``apps/siteconfig/tests/test_sitesettings_slim_contract.py``.

**DB belt-and-suspenders:** when the ``siteconfig_sitesettings`` table exists on the
active connection, physical columns must match the same set (catches half-applied
migrations or manual DDL).
"""

from __future__ import annotations

import re

_TENANT_SETTINGS_MODEL_NAME = "Site" + "Settings"
# Django default table names: lowercase identifier, reasonable length (defense before introspection SQL).
_SLIM_CONTRACT_DB_TABLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")

# ORM local concrete fields and physical DB columns. Today the names align, but the
# contract checks both so db_column drift cannot sneak past the guardrail.
SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES: frozenset[str] = frozenset(
    {"id", "maintenance_mode", "updated_at"}
)
SITESETTINGS_SLIM_LOCAL_CONCRETE_COLUMN_NAMES: frozenset[str] = frozenset(
    {"id", "maintenance_mode", "updated_at"}
)


def _tenant_settings_model():
    import apps.siteconfig.models as _siteconfig_models

    return getattr(_siteconfig_models, _TENANT_SETTINGS_MODEL_NAME)


def _field_name(field) -> str | None:
    name = getattr(field, "name", None)
    if name is None:
        return None
    return str(name)


def _field_column(field) -> str | None:
    column = getattr(field, "column", None)
    if column is None:
        column = getattr(field, "db_column", None)
    if column is None:
        column = getattr(field, "name", None)
    if column is None:
        return None
    return str(column)


def sitesettings_slim_field_errors(
    fields,
    *,
    model_name: str = _TENANT_SETTINGS_MODEL_NAME,
) -> list[str]:
    """Return human-readable errors if a local-concrete field set drifts from the slim-row contract."""
    actual_names = {name for field in fields if (name := _field_name(field)) is not None}
    actual_columns = {
        column for field in fields if (column := _field_column(field)) is not None
    }
    if (
        actual_names == SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES
        and actual_columns == SITESETTINGS_SLIM_LOCAL_CONCRETE_COLUMN_NAMES
    ):
        return []

    missing_names = sorted(SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES - actual_names)
    extra_names = sorted(actual_names - SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES)
    missing_columns = sorted(
        SITESETTINGS_SLIM_LOCAL_CONCRETE_COLUMN_NAMES - actual_columns
    )
    extra_columns = sorted(actual_columns - SITESETTINGS_SLIM_LOCAL_CONCRETE_COLUMN_NAMES)

    parts: list[str] = [
        f"{model_name} slim contract violated (Phase B Batch 0 / 0162). "
        f"Expected local concrete fields {sorted(SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES)!r} "
        f"and columns {sorted(SITESETTINGS_SLIM_LOCAL_CONCRETE_COLUMN_NAMES)!r}."
    ]
    if missing_names:
        parts.append(f"Missing fields: {missing_names}.")
    if extra_names:
        parts.append(
            "Unexpected fields (add bounded-context model + migration; "
            f"do not widen {model_name}): {extra_names}."
        )
    if missing_columns:
        parts.append(f"Missing columns: {missing_columns}.")
    if extra_columns:
        parts.append(f"Unexpected column aliases for {model_name}: {extra_columns}.")
    return [" ".join(parts)]


def sitesettings_slim_model_errors() -> list[str]:
    """Return human-readable errors if the slim-row ORM drifts from the contract."""
    model = _tenant_settings_model()
    return sitesettings_slim_field_errors(
        model._meta.local_concrete_fields,
        model_name=_TENANT_SETTINGS_MODEL_NAME,
    )


def assert_sitesettings_slim_contract() -> None:
    errors = sitesettings_slim_model_errors()
    if errors:
        raise AssertionError(errors[0])


def _invalid_slim_contract_db_table_reason(table: object) -> str | None:
    """Return a human reason if db_table is unsafe for introspection, else None."""
    if not isinstance(table, str):
        return "db_table is not a string."
    normalized = table.strip()
    if not normalized:
        return "db_table is blank."
    if not _SLIM_CONTRACT_DB_TABLE_RE.fullmatch(normalized):
        return f"db_table {normalized!r} is not a safe Django table identifier."
    return None


def sitesettings_slim_db_errors(connection) -> list[str]:
    """
    Compare introspected columns on the slim singleton's DB table to the contract.

    If the table is absent (migrations not applied), returns [] - other gates cover that.
    """
    raw_table = _tenant_settings_model()._meta.db_table
    bad_table = _invalid_slim_contract_db_table_reason(raw_table)
    if bad_table:
        return [f"{_TENANT_SETTINGS_MODEL_NAME} slim DB check: {bad_table}"]
    table = raw_table.strip()
    expected = SITESETTINGS_SLIM_LOCAL_CONCRETE_COLUMN_NAMES

    try:
        tables = connection.introspection.table_names()
    except Exception as exc:
        return [
            f"{_TENANT_SETTINGS_MODEL_NAME} slim DB check: could not list tables: {exc}"
        ]

    if table not in tables:
        return []

    try:
        with connection.cursor() as cursor:
            desc = connection.introspection.get_table_description(cursor, table)
    except Exception as exc:
        return [
            f"{_TENANT_SETTINGS_MODEL_NAME} slim DB check: could not describe table {table!r}: {exc}"
        ]

    actual: set[str] = set()
    for row in desc:
        name = getattr(row, "name", None)
        if name is None and isinstance(row, (tuple, list)) and row:
            name = row[0]
        if isinstance(name, bytes):
            name = name.decode()
        if name is not None:
            actual.add(str(name))

    if actual == expected:
        return []

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    parts = [
        f"{_TENANT_SETTINGS_MODEL_NAME} table {table!r} columns do not match Phase B slim row "
        f"(expected {sorted(expected)!r})."
    ]
    if missing:
        parts.append(f"Missing columns: {missing}.")
    if extra:
        parts.append(
            "Extra columns (drop via migration or you widened "
            f"{_TENANT_SETTINGS_MODEL_NAME} illegally): {extra}."
        )
    return [" ".join(parts)]
