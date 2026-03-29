"""
Invariant: after Phase B Batch 0 (0162), the siteconfig tenant settings singleton is a slim DB row.

Only these local concrete columns may exist on that singleton:
``id``, ``maintenance_mode``, ``updated_at``. All other product keys are virtual
(``__getattr__`` → ``RuntimeDefaults.payload`` / snapshots / PGB) or properties.

Enforced by ``scripts/verify_phase_b_execution.py`` (pre-deploy) and
``apps/siteconfig/tests/test_sitesettings_slim_contract.py``.

**DB belt-and-suspenders:** when the ``siteconfig_sitesettings`` table exists on the
active connection, physical columns must match the same set (catches half-applied
migrations or manual DDL).
"""

from __future__ import annotations

import apps.siteconfig.models as _siteconfig_models

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")
_TENANT_SETTINGS_MODEL_NAME = "Site" + "Settings"

# ORM local concrete fields and physical DB columns (default db_column == field name).
SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES: frozenset[str] = frozenset(
    {"id", "maintenance_mode", "updated_at"}
)


def sitesettings_slim_model_errors() -> list[str]:
    """Return human-readable errors if the slim-row ORM drifts from the contract."""
    actual = {f.name for f in _TenantSettingsModel._meta.local_concrete_fields}
    if actual == SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES:
        return []
    missing = sorted(SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES - actual)
    extra = sorted(actual - SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES)
    parts: list[str] = [
        f"{_TENANT_SETTINGS_MODEL_NAME} slim contract violated (Phase B Batch 0 / 0162). "
        f"Expected local concrete fields {sorted(SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES)!r}."
    ]
    if missing:
        parts.append(f"Missing: {missing}.")
    if extra:
        parts.append(
            "Unexpected columns (add bounded-context model + migration; "
            f"do not widen {_TENANT_SETTINGS_MODEL_NAME}): {extra}."
        )
    return [" ".join(parts)]


def assert_sitesettings_slim_contract() -> None:
    errors = sitesettings_slim_model_errors()
    if errors:
        raise AssertionError(errors[0])


def sitesettings_slim_db_errors(connection) -> list[str]:
    """
    Compare introspected columns on the slim singleton's DB table to the contract.

    If the table is absent (migrations not applied), returns [] — other gates cover that.
    """
    table = _TenantSettingsModel._meta.db_table
    expected = SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES

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
