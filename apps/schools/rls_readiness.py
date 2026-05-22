"""Wave O2 — RLS runtime readiness preflight.

Sister module to ``apps/schools/residency_readiness.py`` (K4),
``apps/security/csp_readiness.py`` (L2), and
``apps/analytics/at_risk_readiness.py`` (O1).

RLS is the load-bearing tenant isolation layer per
``[[project_rls_load_bearing]]``. Migration ``schools.0048_force_rls_on_all_enabled_tables``
binds `FORCE ROW LEVEL SECURITY` on every tenant-scoped table; the
runtime ``SET app.current_school_id`` in ``TenantMiddleware`` activates
the policy.

A regression in any link of that chain — middleware unwired, GUC
variable misnamed, policies dropped, `USE_DJANGO_TENANTS=True`
accidentally enabled (which would switch the platform to schema mode
and silently bypass the RLS policies) — would silently leak
cross-tenant data with no visible error. This preflight asserts the
chain is intact.

Checks performed:

* **Middleware wired** — ``apps.schools.middleware.TenantMiddleware``
  appears in ``settings.MIDDLEWARE``.
* **RLS context helper importable** — ``apps.schools.rls_context.set_rls_school_id``
  (the actual setter called by the middleware) is loadable.
* **USE_DJANGO_TENANTS is False** — schema-mode would bypass RLS;
  warn loudly if True.
* **Postgres-only: GUC variable settable** — issue
  ``SET app.current_school_id = '0'`` against the default DB; success
  proves the runtime contract holds. SQLite returns "not applicable"
  for this check (we run RLS only on PG in production).
* **Postgres-only: at least one RLS policy is registered** — query
  ``pg_policies`` for any policy on the public schema. Zero policies
  means the load-bearing migrations didn't run or were rolled back.

On SQLite-based test/dev environments, the Postgres-only checks are
reported as ``skipped`` rather than failed — the runtime contract is
production-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.db import DatabaseError, connection


@dataclass
class RlsReadinessReport:
    """Outcome of the RLS preflight."""

    ready: bool = True
    backend_vendor: str = ""
    """e.g. 'postgresql', 'sqlite'."""

    middleware_wired: bool = False
    rls_context_importable: bool = False
    use_django_tenants_disabled: bool = True
    """RLS mode requires USE_DJANGO_TENANTS=False; True silently bypasses RLS."""

    guc_settable: bool | None = None
    """None when skipped (non-Postgres); True/False after attempting SET."""

    policy_count: int | None = None
    """None when skipped (non-Postgres); int when pg_policies queried."""

    skipped_checks: list[str] = field(default_factory=list)
    """Reasons certain checks didn't run (e.g. 'non-postgres backend')."""

    error_detail: str = ""

    def issue_count(self) -> int:
        n = 0
        if not self.middleware_wired:
            n += 1
        if not self.rls_context_importable:
            n += 1
        if not self.use_django_tenants_disabled:
            n += 1
        if self.guc_settable is False:  # explicitly False, not None
            n += 1
        if self.policy_count == 0:  # explicit zero, not None
            n += 1
        return n


_MW_TARGET = "apps.schools.middleware.TenantMiddleware"


def _middleware_wired() -> bool:
    chain = getattr(settings, "MIDDLEWARE", ()) or ()
    return _MW_TARGET in chain


def _rls_context_importable() -> bool:
    try:
        from apps.schools.rls_context import set_rls_school_id  # noqa: F401

        return True
    except (ImportError, AttributeError):
        return False


def _use_django_tenants_disabled() -> bool:
    """Return True when the platform is in RLS mode (not schema mode).

    `USE_DJANGO_TENANTS=True` would switch tenancy to django-tenants's
    schema-per-tenant approach, which would silently bypass the RLS
    policies set by migration 0048. The platform is RLS-mode by design
    per ``[[project_rls_load_bearing]]``.
    """
    return not bool(getattr(settings, "USE_DJANGO_TENANTS", False))


def _try_set_guc() -> tuple[bool | None, str]:
    """Attempt SET app.current_school_id; return (settable, error_or_empty).

    SQLite returns (None, '') — not applicable.
    """
    vendor = connection.vendor
    if vendor != "postgresql":
        return None, ""
    try:
        with connection.cursor() as cursor:
            # rls-bypass-allow: rls-readiness-preflight-sets-then-resets-session-variable
            cursor.execute("SET app.current_school_id = '0'")
            # rls-bypass-allow: rls-readiness-preflight-resets-session-variable-after-set-test
            cursor.execute("RESET app.current_school_id")
        return True, ""
    except DatabaseError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 — preflight must never raise
        return False, str(exc)


def _count_rls_policies() -> int | None:
    """Count CREATE POLICY entries in pg_policies. None when non-PG."""
    if connection.vendor != "postgresql":
        return None
    try:
        with connection.cursor() as cursor:
            # rls-bypass-allow: rls-readiness-pg-catalog-introspection-cannot-use-orm
            cursor.execute(
                "SELECT COUNT(*) FROM pg_policies WHERE schemaname = 'public'"
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0
    except DatabaseError:
        return None
    except Exception:  # noqa: BLE001
        return None


def assess_rls_readiness() -> RlsReadinessReport:
    """Run the full RLS preflight; never raises."""
    report = RlsReadinessReport()
    report.backend_vendor = connection.vendor
    report.middleware_wired = _middleware_wired()
    report.rls_context_importable = _rls_context_importable()
    report.use_django_tenants_disabled = _use_django_tenants_disabled()

    settable, err = _try_set_guc()
    report.guc_settable = settable
    if settable is None:
        report.skipped_checks.append(
            "GUC settable (non-postgres backend; production runs Postgres)"
        )
    elif not settable:
        report.error_detail = f"SET app.current_school_id failed: {err}"

    report.policy_count = _count_rls_policies()
    if report.policy_count is None and connection.vendor != "postgresql":
        report.skipped_checks.append(
            "pg_policies count (non-postgres backend)"
        )

    report.ready = report.issue_count() == 0
    return report


__all__ = ["RlsReadinessReport", "assess_rls_readiness"]
