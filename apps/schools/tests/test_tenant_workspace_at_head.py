"""G13 — the workspace probe must tell a healthy tenant from a HALF-migrated one.

``_schema_is_at_head`` compares a schema's applied tenant-migration set against
the code's expected set and requires substantial coverage, so a migrate killed
mid-run (SOME tables, partial django_migrations) no longer reads "present" ->
"ready". The Postgres catalog reads run only under django-tenants (untestable on
the sqlite harness), but the safety-critical DECISION is the pure
``_coverage_is_at_head`` + the clamp on ``_workspace_migration_coverage_floor`` --
both exercised here. The floor is below 1.0 on purpose: a tenant briefly behind a
freshly-deployed migration must NOT be turned into a false "absent" that
re-provisions it.
"""
from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.schools.tenant_workspace import (
    _coverage_is_at_head,
    _workspace_migration_coverage_floor,
)


class CoverageIsAtHeadTests(SimpleTestCase):
    def test_empty_expected_is_never_declared_behind(self):
        # No evidence of what HEAD is -> must not downgrade the schema.
        self.assertTrue(_coverage_is_at_head(set(), set(), 0.9))
        self.assertTrue(_coverage_is_at_head({("academics", "0001")}, set(), 0.9))

    def test_full_coverage_is_at_head(self):
        exp = {("academics", "0001"), ("finance", "0002"), ("people", "0003")}
        self.assertTrue(_coverage_is_at_head(exp, exp, 0.9))

    def test_early_death_partial_is_not_at_head(self):
        exp = {("a", str(i)) for i in range(20)}
        applied = {("a", str(i)) for i in range(6)}  # 30% — migrate died early
        self.assertFalse(_coverage_is_at_head(applied, exp, 0.9))

    def test_post_deploy_drift_above_floor_stays_at_head(self):
        # Healthy tenant briefly behind a couple of just-deployed migrations.
        exp = {("a", str(i)) for i in range(20)}
        applied = {("a", str(i)) for i in range(19)}  # 95% >= 0.9 floor
        self.assertTrue(
            _coverage_is_at_head(applied, exp, 0.9),
            "a tenant behind by a freshly-deployed migration must NOT be re-"
            "provisioned -- the floor tolerates that drift",
        )

    def test_exactly_at_floor_is_at_head(self):
        exp = {("a", str(i)) for i in range(10)}
        applied = {("a", str(i)) for i in range(9)}  # 90% == floor
        self.assertTrue(_coverage_is_at_head(applied, exp, 0.9))


class MigrationCoverageFloorTests(SimpleTestCase):
    def test_default_floor(self):
        self.assertEqual(_workspace_migration_coverage_floor(), 0.9)

    @override_settings(TENANT_WORKSPACE_MIGRATION_COVERAGE_FLOOR=0.2)
    def test_floor_clamped_up_to_half(self):
        # Too-low a floor would let an early-death partial read as at HEAD.
        self.assertEqual(_workspace_migration_coverage_floor(), 0.5)

    @override_settings(TENANT_WORKSPACE_MIGRATION_COVERAGE_FLOOR=1.0)
    def test_floor_clamped_below_one(self):
        # Never demand 100% -> post-deploy drift would storm re-provisions.
        self.assertEqual(_workspace_migration_coverage_floor(), 0.99)

    @override_settings(TENANT_WORKSPACE_MIGRATION_COVERAGE_FLOOR="not-a-number")
    def test_bad_floor_falls_back_to_default(self):
        self.assertEqual(_workspace_migration_coverage_floor(), 0.9)
