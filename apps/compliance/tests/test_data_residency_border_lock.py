"""Border-lock (metric #27) — data sovereignty enforcement is REAL, not soft.

These tests prove that with ``DATA_RESIDENCY_ENFORCE=True`` a region-A tenant
attempting to touch a region-B store is *denied* (a typed ``ResidencyViolation``
→ ``PermissionDenied``) and *audited*, while with the flag off behaviour is
unchanged (no raise, no audit). ``@override_settings`` is used so config/settings
is never edited.

PROVEN LOCALLY 2026-07-02 (fresh SQLite lane): the module runs green 16/16.
The first real run caught that the original unknown-source test asserted a
no-op, but ``effective_region`` never returns blank (defaults ``"global"``),
so the gate fail-closes there — the test was corrected to assert the block.
The historical unknown-region fail-open is now policy-controlled:
``DATA_RESIDENCY_STRICT_UNKNOWN`` — and since the B-validated closeout
(2026-07-03) its UNSET default FOLLOWS ``DATA_RESIDENCY_ENFORCE``: enforcing
deployments fail closed on unknown source/target unless they explicitly opt
out with ``DATA_RESIDENCY_STRICT_UNKNOWN=0``.
CLOSED 2026-07-09 (unresolvable-region closeout): the db-router /
regional-middleware call sites no longer early-return when no alias resolves —
the default-store landing is adjudicated against the declared
``DATA_RESIDENCY_DEFAULT_STORE_REGION`` (default ``"global"``, so
single-region deployments do not brick), and plumbing failures under
enforcement fail CLOSED. See
``apps.compliance.tests.test_residency_unresolvable_region``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase as PlainTestCase
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings

from apps.compliance.cross_border_export import (
    ResidencyViolation,
    cross_border_export_blocked,
    enforce_cross_border_export,
    enforce_region_match,
)


def _school(region: str = "", country: str = ""):
    # SimpleNamespace stands in for a School row — effective_region reads
    # data_region (explicit wins) then country_code; no DB needed.
    return SimpleNamespace(
        slug="alpha-academy",
        pk=1,
        data_region=region,
        country_code=country,
        regional_cluster="",
    )


class EnforceRegionMatchTests(PlainTestCase):
    """Core gate — no DB, no migrations."""

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_strict_blocks_and_audits_cross_region(self, audit_mock):
        school = _school(region="eu_central")
        with self.assertRaises(ResidencyViolation) as ctx:
            enforce_region_match(school, "us_east", kind="db_route")
        # Denial is a PermissionDenied subclass (→ HTTP 403, not a 500).
        self.assertIsInstance(ctx.exception, PermissionDenied)
        self.assertEqual(ctx.exception.source_region, "eu_central")
        self.assertEqual(ctx.exception.target_region, "us_east")
        # The block was audited.
        audit_mock.assert_called_once()
        kwargs = audit_mock.call_args.kwargs
        self.assertEqual(kwargs["source_region"], "eu_central")
        self.assertEqual(kwargs["target_region"], "us_east")
        self.assertEqual(kwargs["kind"], "db_route")

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_strict_allows_same_region(self, audit_mock):
        school = _school(region="eu_central")
        # In-region access is never blocked, even under strict enforcement.
        enforce_region_match(school, "eu_central", kind="db_route")
        audit_mock.assert_not_called()

    @override_settings(DATA_RESIDENCY_ENFORCE=False)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_flag_off_is_noop_even_cross_region(self, audit_mock):
        school = _school(region="eu_central")
        # Backward-compatible default: no raise, no audit.
        enforce_region_match(school, "us_east", kind="db_route")
        audit_mock.assert_not_called()

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_strict_blocks_unknown_source_resolved_global(self, audit_mock):
        # No data_region and no country: effective_region() NEVER returns blank —
        # derive_default_region("") falls back to GLOBAL_DATA_REGION — so an
        # unregistered tenant is still fail-CLOSED against a known foreign
        # region. (Replaces test_strict_noop_when_region_unknown, which encoded
        # a wrong model of effective_region and failed on first real run.)
        school = _school(region="", country="")
        with self.assertRaises(ResidencyViolation) as ctx:
            enforce_region_match(school, "us_east", kind="db_route")
        self.assertEqual(ctx.exception.source_region, "global")
        self.assertEqual(ctx.exception.target_region, "us_east")
        audit_mock.assert_called_once()

    @override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=None)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_enforce_alone_now_blocks_blank_target_by_default(self, audit_mock):
        # B-validated closeout: the unset strict-unknown default FOLLOWS
        # enforcement — the originally-cited fail-open (ENFORCE=1 alone,
        # blank destination silently passes) is closed by default.
        school = _school(region="eu_central")
        with self.assertRaises(ResidencyViolation):
            enforce_region_match(school, "", kind="db_route")
        audit_mock.assert_called_once()

    @override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=False)
    def test_explicit_opt_out_restores_unknown_pass(self):
        # Single-region-shaped deployments opt out EXPLICITLY, never silently.
        school = _school(region="eu_central")
        enforce_region_match(school, None, kind="db_route")  # no raise
        enforce_region_match(school, "", kind="db_route")  # no raise

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    def test_strict_noop_when_no_school(self):
        enforce_region_match(None, "us_east", kind="db_route")  # no raise

    @override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_strict_unknown_blocks_blank_target(self, audit_mock):
        # Strict-sovereignty posture: an unknown TARGET region can no longer
        # silently pass — the historical fail-open this flag exists to close.
        school = _school(region="eu_central")
        with self.assertRaises(ResidencyViolation) as ctx:
            enforce_region_match(school, "", kind="db_route")
        self.assertEqual(ctx.exception.source_region, "eu_central")
        self.assertEqual(ctx.exception.target_region, "unknown")
        audit_mock.assert_called_once()

    @override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_strict_unknown_blocks_unresolvable_source(self, audit_mock):
        # The only reachable blank-source arm: resolution RAISES and the raw
        # field is also empty. Strict mode blocks instead of passing.
        school = _school(region="", country="")
        with patch(
            "apps.schools.data_residency.effective_region",
            side_effect=RuntimeError("resolver down"),
        ):
            with self.assertRaises(ResidencyViolation) as ctx:
                enforce_region_match(school, "us_east", kind="export")
        self.assertEqual(ctx.exception.source_region, "unknown")
        self.assertEqual(ctx.exception.target_region, "us_east")
        audit_mock.assert_called_once()

    @override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=True)
    def test_strict_unknown_still_allows_matching_regions(self):
        school = _school(region="eu_central")
        enforce_region_match(school, "eu_central", kind="db_route")  # no raise


class CrossBorderExportTests(PlainTestCase):
    """The export-facing twins — soft predicate + fail-closed enforcer."""

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    def test_export_strict_blocks(self):
        school = _school(region="eu_central")
        blocked, msg = cross_border_export_blocked(
            school, destination_region="us_east"
        )
        self.assertTrue(blocked)
        self.assertIn("blocked", msg.lower())

    @override_settings(DATA_RESIDENCY_ENFORCE=False)
    def test_export_soft_allows_mismatch(self):
        school = _school(region="eu_central")
        blocked, _ = cross_border_export_blocked(
            school, destination_region="us_east"
        )
        self.assertFalse(blocked)

    @override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=None)
    def test_export_predicate_agrees_with_enforcer_on_blank_destination(self):
        # The UI-greying predicate and the fail-closed gate must never
        # disagree: blank destination under default-strict enforcement greys
        # the button too.
        school = _school(region="eu_central")
        blocked, msg = cross_border_export_blocked(school, destination_region="")
        self.assertTrue(blocked)
        self.assertIn("unknown", msg.lower())

    @override_settings(DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=False)
    def test_export_predicate_honors_explicit_opt_out(self):
        school = _school(region="eu_central")
        blocked, _ = cross_border_export_blocked(school, destination_region="")
        self.assertFalse(blocked)

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_enforce_export_raises_on_cross_border(self, _audit_mock):
        school = _school(region="eu_central")
        with self.assertRaises(ResidencyViolation):
            enforce_cross_border_export(school, destination_region="us_east")

    @override_settings(DATA_RESIDENCY_ENFORCE=False)
    def test_enforce_export_noop_when_flag_off(self):
        school = _school(region="eu_central")
        enforce_cross_border_export(school, destination_region="us_east")  # no raise


class RouterBorderLockTests(PlainTestCase):
    """The DB router is the choke point: a foreign-region alias is blocked.

    The active tenant is read from ``connection.tenant``; the resolved alias is
    the region the op would be served from. We mock both so no DB is needed.
    """

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_db_for_write_blocks_foreign_alias(self, _audit_mock):
        from apps.siteconfig import db_router

        tenant = SimpleNamespace(school=_school(region="eu_central"))
        with patch.object(db_router, "_get_tenant_db_alias", return_value="us_east"), \
                patch("django.db.connection") as conn:
            conn.tenant = tenant
            router = db_router.TenantDatabaseRouter()
            with self.assertRaises(ResidencyViolation):
                router.db_for_write(object)

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_db_for_write_allows_in_region_alias(self, audit_mock):
        from apps.siteconfig import db_router

        tenant = SimpleNamespace(school=_school(region="eu_central"))
        with patch.object(db_router, "_get_tenant_db_alias", return_value="eu_central"), \
                patch("django.db.connection") as conn:
            conn.tenant = tenant
            router = db_router.TenantDatabaseRouter()
            self.assertEqual(router.db_for_write(object), "eu_central")
        audit_mock.assert_not_called()

    @override_settings(DATA_RESIDENCY_ENFORCE=False)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_db_for_write_noop_when_flag_off(self, audit_mock):
        from apps.siteconfig import db_router

        tenant = SimpleNamespace(school=_school(region="eu_central"))
        with patch.object(db_router, "_get_tenant_db_alias", return_value="us_east"), \
                patch("django.db.connection") as conn:
            conn.tenant = tenant
            router = db_router.TenantDatabaseRouter()
            # Flag off → unchanged: returns the alias, never raises/audits.
            self.assertEqual(router.db_for_write(object), "us_east")
        audit_mock.assert_not_called()


class MiddlewareBorderLockTests(PlainTestCase):
    """The regional middleware blocks a pre-pinned foreign-region request."""

    @override_settings(DATA_RESIDENCY_ENFORCE=True, ENABLE_MULTI_REGION=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_middleware_blocks_pre_pinned_foreign_region(self, _audit_mock):
        from apps.platform_runtime.middleware_regional_db import (
            RegionalDatabaseMiddleware,
        )
        from apps.platform_runtime import dynamic_db_routing as ddr

        request = SimpleNamespace(school=_school(region="eu_central"))
        ddr.set_request_db_alias("us_east")  # upstream pinned a foreign region
        try:
            mw = RegionalDatabaseMiddleware(lambda r: "OK")
            with self.assertRaises(ResidencyViolation):
                mw(request)
        finally:
            ddr.clear_request_db_alias()

    @override_settings(DATA_RESIDENCY_ENFORCE=False, ENABLE_MULTI_REGION=True)
    def test_middleware_noop_when_flag_off(self):
        from apps.platform_runtime.middleware_regional_db import (
            RegionalDatabaseMiddleware,
        )
        from apps.platform_runtime import dynamic_db_routing as ddr

        request = SimpleNamespace(school=_school(region="eu_central"))
        ddr.set_request_db_alias("us_east")
        try:
            mw = RegionalDatabaseMiddleware(lambda r: "OK")
            self.assertEqual(mw(request), "OK")  # unchanged, no raise
        finally:
            ddr.clear_request_db_alias()


class AuditTrailWriteTests(TestCase):
    """DB-TOUCHING: proves the block writes a real ACCESS_DENIED AuditLog row.

    Isolated in a django.test.TestCase because it hits the DB. UNPROVEN LOCALLY
    (env) per the moderator note — runs in CI.
    """

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    def test_violation_writes_access_denied_audit_row(self):
        from apps.compliance.models_audit import AuditLog

        before = AuditLog.objects.filter(
            action=AuditLog.Action.ACCESS_DENIED, app_label="compliance"
        ).count()
        school = _school(region="eu_central")
        with self.assertRaises(ResidencyViolation):
            enforce_region_match(school, "us_east", kind="db_route")
        after = AuditLog.objects.filter(
            action=AuditLog.Action.ACCESS_DENIED, app_label="compliance"
        ).count()
        self.assertEqual(after, before + 1)
        row = AuditLog.objects.filter(
            action=AuditLog.Action.ACCESS_DENIED, app_label="compliance"
        ).latest("timestamp")
        self.assertEqual(row.sensitivity, AuditLog.Sensitivity.CRITICAL)
        self.assertIn("us_east", row.reason)
        self.assertIn("eu_central", row.reason)
