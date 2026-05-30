"""v4.00.83 Wave 15 T3 — TenantRetentionOverride model + resolver smoke.

Per-tenant overrides for retention sweep windows. The resolver follows
this lookup precedence:

  1. TenantRetentionOverride row for (tenant, target_table) -> years
  2. Env RMC_LMS_RETENTION_<TABLE>_YEARS
  3. Default 7 years (FERPA)

Pattern: dev DB via ``config.settings`` (mirror Wave 12 T4 DLQ pattern —
``config.settings_test`` runs in-memory SQLite which on Windows takes
5+ minutes to spin up the full migration history; not acceptable for
a per-target smoke).

Cases:

  1. Model imports + DB-reachable (verify resolver default)
  2. resolve_retention_years(acme, lms_diag_action_audit) -> 7 (default)
  3. Env RMC_LMS_RETENTION_DIAG_ACTION_AUDIT_YEARS=3 -> resolver returns 3
  4. set_tenant_retention_override(acme, ..., 10, "NY state law", "admin1") -> row
  5. resolver returns 10 (override wins over default)
  6. Override still wins even when env still set to 3 -> 10
  7. resolve_retention_years(other_tenant, ...) -> 7 (other tenant unaffected)
  8. Update existing override to 5 -> same row updated (UniqueConstraint)
  9. set_tenant_retention_override(..., 0) -> retain-forever value persisted
 10. Bad numeric env value -> resolver falls back to default 7
 11. UniqueConstraint enforced: 1 row per (tenant, table) — verify count
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import django  # noqa: E402

django.setup()

# Clear any pre-existing env override so default-path cases are deterministic.
_ENV_KEY = "RMC_LMS_RETENTION_DIAG_ACTION_AUDIT_YEARS"
os.environ.pop(_ENV_KEY, None)


CASES = 0


def _ok(label):
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


print("=" * 70)
print("v4.00.83 Wave 15 T3 — TenantRetentionOverride model + resolver smoke")
print("=" * 70)


# --------------------------------------------------------------------------
# Case 1: Model imports + table reachable (migration 0006 applied on dev DB)
# --------------------------------------------------------------------------
from apps.integrations_marketplace.models import TenantRetentionOverride  # noqa: E402
from apps.integrations_marketplace.lms_retention_resolver import (  # noqa: E402
    DEFAULT_RETENTION_YEARS,
    resolve_retention_years,
    set_tenant_retention_override,
)

# Clean up any prior smoke fixtures so re-runs stay idempotent.
TenantRetentionOverride.objects.filter(
    tenant_schema__in=["smoke_acme", "smoke_other_tenant"],
).delete()

assert DEFAULT_RETENTION_YEARS == 7, DEFAULT_RETENTION_YEARS
_ok(f"model imports + DEFAULT_RETENTION_YEARS={DEFAULT_RETENTION_YEARS}")


# --------------------------------------------------------------------------
# Case 2: No override + no env -> default 7
# --------------------------------------------------------------------------
years = resolve_retention_years(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
)
assert years == 7, years
_ok(f"resolve (no override, no env) -> {years}")


# --------------------------------------------------------------------------
# Case 3: Env set to 3 -> resolver returns 3
# --------------------------------------------------------------------------
os.environ[_ENV_KEY] = "3"
years = resolve_retention_years(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
)
assert years == 3, years
_ok(f"resolve (env=3, no override) -> {years}")


# --------------------------------------------------------------------------
# Case 4: set_tenant_retention_override creates a row
# Clear env first so this case isolates the override path on the way in.
# --------------------------------------------------------------------------
os.environ.pop(_ENV_KEY, None)
row = set_tenant_retention_override(
    tenant_schema="smoke_acme",
    target_table="lms_diag_action_audit",
    retention_years=10,
    reason="NY state law",
    set_by_actor_id="admin1",
)
assert row is not None, "set_tenant_retention_override returned None"
assert row.tenant_schema == "smoke_acme"
assert row.target_table == "lms_diag_action_audit"
assert row.retention_years == 10
assert row.reason == "NY state law"
assert row.set_by_actor_id == "admin1"
_ok(f"set_tenant_retention_override created row id={row.pk} years=10")


# --------------------------------------------------------------------------
# Case 5: resolver now returns 10 (override > default)
# --------------------------------------------------------------------------
years = resolve_retention_years(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
)
assert years == 10, years
_ok(f"resolve (override=10, no env) -> {years}")


# --------------------------------------------------------------------------
# Case 6: Override still wins when env also set to 3
# --------------------------------------------------------------------------
os.environ[_ENV_KEY] = "3"
years = resolve_retention_years(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
)
assert years == 10, f"override should beat env, got {years}"
_ok(f"resolve (override=10, env=3) -> {years} [override wins]")


# --------------------------------------------------------------------------
# Case 7: Other tenant -> falls through override to env (3)
# (Different tenant with no override, env still set to 3.)
# --------------------------------------------------------------------------
years = resolve_retention_years(
    tenant_schema="smoke_other_tenant", target_table="lms_diag_action_audit",
)
assert years == 3, f"other tenant should hit env=3, got {years}"
_ok(f"resolve (other tenant, env=3) -> {years}")

# Now clear the env -> other tenant gets default 7
os.environ.pop(_ENV_KEY, None)
years = resolve_retention_years(
    tenant_schema="smoke_other_tenant", target_table="lms_diag_action_audit",
)
assert years == 7, years
_ok(f"resolve (other tenant, no env, no override) -> {years}")


# --------------------------------------------------------------------------
# Case 8: Update existing override -> same row updated (UniqueConstraint)
# --------------------------------------------------------------------------
row_again = set_tenant_retention_override(
    tenant_schema="smoke_acme",
    target_table="lms_diag_action_audit",
    retention_years=5,
    reason="updated rule",
)
assert row_again is not None
assert row_again.pk == row.pk, (
    f"expected same row updated, got pk={row_again.pk} vs original {row.pk}"
)
assert row_again.retention_years == 5
# Verify only one row exists for (tenant, table)
count = TenantRetentionOverride.objects.filter(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
).count()
assert count == 1, f"UniqueConstraint failed: {count} rows"
years = resolve_retention_years(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
)
assert years == 5, years
_ok(f"update_or_create updated existing row (count={count}, years now {years})")


# --------------------------------------------------------------------------
# Case 9: retention_years=0 -> retain-forever value persisted
# --------------------------------------------------------------------------
row_zero = set_tenant_retention_override(
    tenant_schema="smoke_acme",
    target_table="lms_diag_action_audit",
    retention_years=0,
    reason="retain forever",
)
assert row_zero is not None
assert row_zero.retention_years == 0, row_zero.retention_years
years = resolve_retention_years(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
)
assert years == 0, f"retain-forever should be 0, got {years}"
_ok(f"set_tenant_retention_override(retention_years=0) -> resolve returns {years}")


# --------------------------------------------------------------------------
# Case 10: Bad numeric env value -> resolver falls back to default 7
# (Clear the override first so we exercise the env path.)
# --------------------------------------------------------------------------
TenantRetentionOverride.objects.filter(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
).delete()
os.environ[_ENV_KEY] = "not-a-number"
years = resolve_retention_years(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
)
assert years == 7, f"bad env should fall to default 7, got {years}"
_ok(f"resolve (env='not-a-number') -> {years} [fell back to default]")
os.environ.pop(_ENV_KEY, None)


# --------------------------------------------------------------------------
# Case 11: UniqueConstraint enforced — 1 row per (tenant, table)
# Repeated set_tenant_retention_override calls do NOT create duplicates.
# --------------------------------------------------------------------------
for n_years in (4, 6, 8, 12):
    set_tenant_retention_override(
        tenant_schema="smoke_acme",
        target_table="lms_diag_action_audit",
        retention_years=n_years,
    )
count = TenantRetentionOverride.objects.filter(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
).count()
assert count == 1, f"UniqueConstraint failed: {count} rows after 4 sets"
# And the value reflects the LAST set
last = TenantRetentionOverride.objects.get(
    tenant_schema="smoke_acme", target_table="lms_diag_action_audit",
)
assert last.retention_years == 12, last.retention_years
_ok(f"UniqueConstraint enforced: 1 row per (tenant, table) after 4 sets")


# Cleanup smoke fixtures from the dev DB so re-runs stay idempotent.
TenantRetentionOverride.objects.filter(
    tenant_schema__in=["smoke_acme", "smoke_other_tenant"],
).delete()


print("=" * 70)
print(f"v4.00.83 Wave 15 T3 — retention override smoke OK ({CASES}/{CASES} cases)")
print("=" * 70)
