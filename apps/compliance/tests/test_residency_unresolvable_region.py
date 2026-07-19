"""Unresolvable-region closeout (2026-07-09) — the routing layers fail CLOSED.

The border-lock hard gate (``enforce_region_match``) was already fail-closed,
but the three routing layers that CALL it still early-returned when no region
could be resolved, so under ``DATA_RESIDENCY_ENFORCE`` a tenant with a foreign
residency promise was silently served from the default store:

* ``TenantDatabaseRouter`` skipped the check entirely when no alias resolved,
  and swallowed plumbing failures;
* ``RegionalDatabaseMiddleware`` silently default-routed when the school's
  region store was unprovisioned;
* ``DataResidencyMiddleware`` swallowed a crashed alignment check even in
  strict mode, and treated a blank operational binding as aligned.

This battery proves the closeout: the default-store landing is adjudicated
against the DECLARED ``DATA_RESIDENCY_DEFAULT_STORE_REGION`` (default
``"global"`` — matching the readiness preflight's "global is served by the
default DB by definition", so single-region deployments do not brick), replica
aliases (``replica_<region>``) map to their region instead of spuriously
blocking, plumbing failures under enforcement DENY (mirroring ``pdp_enforce``),
and the router's reentrancy guard stops the audit-write recursion. Flag-off
behaviour is unchanged everywhere.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest import TestCase as PlainTestCase
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import override_settings

from apps.compliance.cross_border_export import ResidencyViolation
from apps.schools.data_residency import (
    CrossRegionWriteError,
    assert_aligned_or_log,
    default_store_region,
    region_for_alias,
)


def _school(region: str = "", country: str = "", cluster: str = ""):
    # SimpleNamespace stands in for a School row — effective_region reads
    # data_region (explicit wins) then country_code; no DB needed.
    return SimpleNamespace(
        slug="alpha-academy",
        pk=1,
        data_region=region,
        country_code=country,
        regional_cluster=cluster,
    )


class RegionForAliasTests(PlainTestCase):
    """Alias → region mapping: the piece that makes every path comparable."""

    def test_replica_prefix_maps_to_its_region(self):
        # Wave-K4 env registration names replicas replica_<region>; the border
        # lock must not spuriously block a tenant on its OWN replica.
        self.assertEqual(region_for_alias("replica_eu_central"), "eu_central")

    def test_region_named_alias_passes_through(self):
        self.assertEqual(region_for_alias("us_east"), "us_east")

    def test_blank_and_default_resolve_to_declared_store_region(self):
        # Deployed default: the default store is declared "global".
        self.assertEqual(region_for_alias(None), "global")
        self.assertEqual(region_for_alias(""), "global")
        self.assertEqual(region_for_alias("default"), "global")
        self.assertEqual(default_store_region(), "global")

    @override_settings(DATA_RESIDENCY_DEFAULT_STORE_REGION="eu_central")
    def test_declared_default_store_region_setting_is_honored(self):
        self.assertEqual(default_store_region(), "eu_central")
        self.assertEqual(region_for_alias(None), "eu_central")

    @override_settings(DATA_RESIDENCY_DEFAULT_STORE_REGION="eu_central")
    @patch.dict(
        "os.environ", {"DATA_RESIDENCY_DEFAULT_STORE_REGION": "us_east"}, clear=False
    )
    def test_env_wins_over_setting_for_default_store_region(self):
        # Ops can re-declare the default store without a redeploy.
        self.assertEqual(default_store_region(), "us_east")


class RouterUnresolvedAliasTests(PlainTestCase):
    """The router no longer skips the check when NO alias resolves."""

    def _router_with_tenant(self, school, alias):
        from apps.siteconfig import db_router

        tenant = SimpleNamespace(school=school)
        ctx_alias = patch.object(db_router, "_get_tenant_db_alias", return_value=alias)
        ctx_conn = patch("django.db.connection")
        return db_router, tenant, ctx_alias, ctx_conn

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_foreign_promise_on_default_store_is_blocked(self, audit_mock):
        # THE closed hole: eu_central promise, no replica provisioned, op about
        # to land on the default (global) store → denied, not silently served.
        db_router, tenant, ctx_alias, ctx_conn = self._router_with_tenant(
            _school(region="eu_central"), None
        )
        with ctx_alias, ctx_conn as conn:
            conn.tenant = tenant
            with self.assertRaises(ResidencyViolation) as ctx:
                db_router.TenantDatabaseRouter().db_for_write(object)
        self.assertEqual(ctx.exception.source_region, "eu_central")
        self.assertEqual(ctx.exception.target_region, "global")
        audit_mock.assert_called_once()

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_global_tenant_on_default_store_passes(self, audit_mock):
        # Single-region deployments do not brick: an unregistered tenant
        # resolves "global", the default store is declared "global" → allowed.
        db_router, tenant, ctx_alias, ctx_conn = self._router_with_tenant(
            _school(region="", country=""), None
        )
        with ctx_alias, ctx_conn as conn:
            conn.tenant = tenant
            self.assertIsNone(db_router.TenantDatabaseRouter().db_for_write(object))
        audit_mock.assert_not_called()

    @override_settings(
        DATA_RESIDENCY_ENFORCE=True,
        DATA_RESIDENCY_DEFAULT_STORE_REGION="eu_central",
    )
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_declared_default_store_region_admits_matching_tenant(self, audit_mock):
        # A deployment whose primary IS the eu_central store declares it and
        # its in-region tenants keep working with zero replicas.
        db_router, tenant, ctx_alias, ctx_conn = self._router_with_tenant(
            _school(region="eu_central"), None
        )
        with ctx_alias, ctx_conn as conn:
            conn.tenant = tenant
            self.assertIsNone(db_router.TenantDatabaseRouter().db_for_write(object))
        audit_mock.assert_not_called()

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_own_region_replica_alias_is_not_spuriously_blocked(self, audit_mock):
        # replica_eu_central serves eu_central — comparing the raw alias name
        # would have blocked a correctly-provisioned deployment.
        db_router, tenant, ctx_alias, ctx_conn = self._router_with_tenant(
            _school(region="eu_central"), "replica_eu_central"
        )
        with ctx_alias, ctx_conn as conn:
            conn.tenant = tenant
            self.assertEqual(
                db_router.TenantDatabaseRouter().db_for_write(object),
                "replica_eu_central",
            )
        audit_mock.assert_not_called()

    @override_settings(DATA_RESIDENCY_ENFORCE=False)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_flag_off_keeps_unresolved_alias_passing(self, audit_mock):
        # Backward-compatible default: enforcement off → no check, no audit.
        db_router, tenant, ctx_alias, ctx_conn = self._router_with_tenant(
            _school(region="eu_central"), None
        )
        with ctx_alias, ctx_conn as conn:
            conn.tenant = tenant
            self.assertIsNone(db_router.TenantDatabaseRouter().db_for_write(object))
        audit_mock.assert_not_called()


class RouterFailClosedTests(PlainTestCase):
    """Plumbing failure under enforcement DENIES; and the reentrancy guard."""

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    def test_plumbing_failure_denies_under_enforcement(self):
        from apps.siteconfig import db_router

        tenant = SimpleNamespace(school=_school(region="eu_central"))
        with patch.object(db_router, "_get_tenant_db_alias", return_value=None), patch(
            "django.db.connection"
        ) as conn, patch(
            "apps.compliance.cross_border_export.enforce_region_match",
            side_effect=TypeError("resolver exploded"),
        ):
            conn.tenant = tenant
            with self.assertRaises(PermissionDenied) as ctx:
                db_router.TenantDatabaseRouter().db_for_write(object)
        self.assertNotIsInstance(ctx.exception, ResidencyViolation)
        self.assertIn("unavailable", str(ctx.exception).lower())

    @override_settings(DATA_RESIDENCY_ENFORCE=False)
    def test_plumbing_failure_stays_silent_when_flag_off(self):
        from apps.siteconfig import db_router

        tenant = SimpleNamespace(school=_school(region="eu_central"))
        with patch.object(
            db_router, "_get_tenant_db_alias", return_value="eu_central"
        ), patch("django.db.connection") as conn, patch(
            "apps.compliance.cross_border_export.enforce_region_match",
            side_effect=TypeError("resolver exploded"),
        ):
            conn.tenant = tenant
            # Flag off → the check is never consulted; the alias is returned.
            self.assertEqual(
                db_router.TenantDatabaseRouter().db_for_write(object), "eu_central"
            )

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_reentrant_orm_op_from_the_check_is_not_re_adjudicated(self, _audit):
        # The check itself performs ORM ops (region resolution reads, the
        # violation AuditLog write). Each re-enters db_for_write; without the
        # guard that recursion is unbounded (audit → router → audit → …).
        from apps.siteconfig import db_router

        tenant = SimpleNamespace(school=_school(region="eu_central"))
        router = db_router.TenantDatabaseRouter()
        calls = []

        def _reentrant_enforce(school, target, kind=""):
            calls.append(target)
            # Simulates the audit write the gate performs while blocking:
            # must NOT re-enter enforcement (would recurse), must route.
            inner = router.db_for_write(object)
            self.assertIsNone(inner)
            raise ResidencyViolation("blocked", source_region="eu_central",
                                     target_region=str(target))

        with patch.object(db_router, "_get_tenant_db_alias", return_value=None), patch(
            "django.db.connection"
        ) as conn, patch(
            "apps.compliance.cross_border_export.enforce_region_match",
            side_effect=_reentrant_enforce,
        ):
            conn.tenant = tenant
            with self.assertRaises(ResidencyViolation):
                router.db_for_write(object)
        self.assertEqual(len(calls), 1)  # adjudicated exactly once


class RegionalMiddlewareUnresolvedTests(PlainTestCase):
    """Request-time twin: unprovisioned region store is refused up front."""

    def _mw_request(self, school):
        from apps.platform_runtime.middleware_regional_db import (
            RegionalDatabaseMiddleware,
        )

        return RegionalDatabaseMiddleware(lambda r: "OK"), SimpleNamespace(
            school=school
        )

    @override_settings(DATA_RESIDENCY_ENFORCE=True, ENABLE_MULTI_REGION=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_foreign_promise_with_no_region_store_is_refused(self, audit_mock):
        # No DATABASES alias exists for eu_central in the test settings, so
        # the school's region store is genuinely unresolvable here.
        mw, request = self._mw_request(_school(region="eu_central"))
        with self.assertRaises(ResidencyViolation) as ctx:
            mw(request)
        self.assertEqual(ctx.exception.target_region, "global")
        audit_mock.assert_called_once()

    @override_settings(DATA_RESIDENCY_ENFORCE=True, ENABLE_MULTI_REGION=True)
    def test_global_tenant_still_served(self):
        mw, request = self._mw_request(_school(region="", country=""))
        self.assertEqual(mw(request), "OK")

    @override_settings(
        DATA_RESIDENCY_ENFORCE=True,
        ENABLE_MULTI_REGION=True,
        DATA_RESIDENCY_DEFAULT_STORE_REGION="eu_central",
    )
    def test_declared_default_store_admits_matching_tenant(self):
        mw, request = self._mw_request(_school(region="eu_central"))
        self.assertEqual(mw(request), "OK")

    @override_settings(DATA_RESIDENCY_ENFORCE=False, ENABLE_MULTI_REGION=True)
    def test_flag_off_keeps_unresolved_request_passing(self):
        mw, request = self._mw_request(_school(region="eu_central"))
        self.assertEqual(mw(request), "OK")

    @override_settings(DATA_RESIDENCY_ENFORCE=True, ENABLE_MULTI_REGION=False)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_foreign_promise_refused_even_when_multi_region_off(self, audit_mock):
        """Default-store adjudication must not require ENABLE_MULTI_REGION."""
        mw, request = self._mw_request(_school(region="eu_central"))
        with self.assertRaises(ResidencyViolation) as ctx:
            mw(request)
        self.assertEqual(ctx.exception.target_region, "global")
        audit_mock.assert_called_once()

    @override_settings(DATA_RESIDENCY_ENFORCE=False, ENABLE_MULTI_REGION=False)
    def test_multi_region_off_soft_when_enforce_off(self):
        mw, request = self._mw_request(_school(region="eu_central"))
        self.assertEqual(mw(request), "OK")


class DataResidencyMiddlewareFailClosedTests(PlainTestCase):
    """The alignment middleware: blank binding adjudicated; crashes fail closed."""

    def _mw(self):
        from apps.schools.middleware_residency import DataResidencyMiddleware

        return DataResidencyMiddleware(lambda r: "OK")

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_blank_binding_foreign_promise_is_refused(self, audit_mock):
        # regional_cluster blank = served from the default store; historically
        # "aligned" ("no promise broken yet") — the closed fail-open.
        request = SimpleNamespace(school=_school(region="eu_central", cluster=""))
        with self.assertRaises(ResidencyViolation):
            self._mw()(request)
        audit_mock.assert_called_once()

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    def test_blank_binding_global_tenant_still_served(self):
        request = SimpleNamespace(school=_school(region="", country="", cluster=""))
        self.assertEqual(self._mw()(request), "OK")

    def test_blank_binding_stays_soft_when_flag_off(self):
        request = SimpleNamespace(school=_school(region="eu_central", cluster=""))
        self.assertEqual(self._mw()(request), "OK")

    @override_settings(DATA_RESIDENCY_ENFORCE=True)
    def test_crashed_check_fails_closed_under_enforcement(self):
        request = SimpleNamespace(school=_school(region="eu_central", cluster=""))
        with patch(
            "apps.schools.data_residency.assert_aligned_or_log",
            side_effect=RuntimeError("alignment check exploded"),
        ):
            with self.assertRaises(PermissionDenied) as ctx:
                self._mw()(request)
        self.assertIn("unavailable", str(ctx.exception).lower())

    def test_crashed_check_still_swallowed_when_flag_off(self):
        request = SimpleNamespace(school=_school(region="eu_central", cluster=""))
        logging.disable(logging.CRITICAL)
        try:
            with patch(
                "apps.schools.data_residency.assert_aligned_or_log",
                side_effect=RuntimeError("alignment check exploded"),
            ):
                self.assertEqual(self._mw()(request), "OK")
        finally:
            logging.disable(logging.NOTSET)


class AssertAlignedEnvAwareTests(PlainTestCase):
    """assert_aligned_or_log honours the env-or-setting enforcement contract."""

    @patch.dict("os.environ", {"DATA_RESIDENCY_ENFORCE": "1"}, clear=False)
    def test_env_flag_alone_binds_the_mismatch_arm(self):
        # Previously read the raw Django setting only, so an ops env flip
        # enforced the border lock but left this middleware soft-logging.
        school = _school(region="eu_central", cluster="us_east")
        with self.assertRaises(CrossRegionWriteError):
            assert_aligned_or_log(school)

    @override_settings(
        DATA_RESIDENCY_ENFORCE=True, DATA_RESIDENCY_STRICT_UNKNOWN=False
    )
    @patch("apps.compliance.cross_border_export._audit_residency_violation")
    def test_blank_binding_block_is_a_known_comparison_not_strict_unknown(
        self, audit_mock
    ):
        # Declaring the default store's region makes the blank-binding case a
        # KNOWN mismatch (eu_central vs global) — the strict-unknown opt-out
        # deliberately does not reopen it.
        school = _school(region="eu_central", cluster="")
        with self.assertRaises(ResidencyViolation):
            assert_aligned_or_log(school)
        audit_mock.assert_called_once()

    def test_soft_mode_mismatch_still_warns_not_raises(self):
        school = _school(region="eu_central", cluster="us_east")
        with self.assertLogs("apps.schools.data_residency", level="WARNING"):
            assert_aligned_or_log(school)
