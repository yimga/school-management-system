"""Test-support helpers for running `tenants_rls`-tagged tests under real RLS.

Background
----------
In RLS single-schema mode (``USE_DJANGO_TENANTS=0`` on PostgreSQL) every
tenant table is FORCE'd + default-deny: a row is visible/insertable only when
the connection carries ``app.current_school_id`` (matching the row) or
``app.rls_bypass = 'on'``. In production that GUC is set per HTTP request by
``apps/schools/middleware.py`` / ``apps/tenancy/middleware_rls_jwt.py``.

Most ``tenants_rls``-tagged tests, however, bypass the request cycle: they
build rows directly via the ORM in ``setUp`` and assert on them in the test
body. Many carry the tag ONLY to route the file onto the Postgres CI lane
(query-count regressions, DB-exclusion constraints, service logic) and are not
exercising the RLS policy itself. With no GUC set, their seed INSERTs and reads
hit default-deny and the test errors ("Save did not affect any rows" /
``DoesNotExist`` / empty result) the moment RLS actually binds for a
non-superuser connection.

``enter_rls_bypass_for_test`` runs such a test under ``app.rls_bypass`` for its
whole duration, so RLS does not interfere with what the test is actually
verifying. The DATABASE RLS policy is proven separately and on purpose by
``apps/schools/tests/test_tenant_isolation_rls_mode.py`` (unset→deny,
set→restrict, bypass→all) and ``apps/schools/tests/test_rls_force_coverage.py``
(every enabled+policied table is FORCE'd). Do NOT add this helper to a test
that is meant to assert cross-tenant isolation at the DB layer — those must set
per-school context, not bypass.

No-op on SQLite and under schema-per-tenant mode (``rls_bypass`` yields without
touching the connection there), so this is inert on the SQLite CI lane.
"""

from __future__ import annotations

from apps.schools.rls_context import rls_bypass


def enter_rls_bypass_for_test(testcase) -> None:
    """Enter ``app.rls_bypass`` for the rest of the test, auto-reset on cleanup.

    Call as the FIRST line of ``setUp`` (before any ORM writes), so both the
    seed data and the test-body reads run with RLS bypassed. Registers the
    reset via ``addCleanup`` so it fires after the test regardless of outcome.
    """
    cm = rls_bypass()
    cm.__enter__()
    testcase.addCleanup(cm.__exit__, None, None, None)
