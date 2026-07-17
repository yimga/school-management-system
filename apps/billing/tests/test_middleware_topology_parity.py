"""Middleware declared in the base MIDDLEWARE must also load in the tenants topology.

config/settings.py builds MIDDLEWARE at module level, then — inside
``if USE_DJANGO_TENANTS and postgresql`` — REPLACES it wholesale. Production sets
USE_DJANGO_TENANTS=1 on Postgres and nothing mutates MIDDLEWARE afterwards, so the
base list is dead code in prod and the tenants list is the only one that runs.

That makes the pair a hand-maintained duplicate, and it had drifted: the finance
subscription gate and the db_sessions metering middleware were added to the base
list only, so both were inert in production while looking wired in review. Worse,
the test suite runs on SQLite, which takes the *base* branch — so a gate that never
fires in prod still goes green here. That is why this test asserts against the
parsed settings source rather than ``django.conf.settings.MIDDLEWARE``: reading the
live setting under the test runner would only ever see the base list and could
never catch the drift it exists to catch.
"""

from __future__ import annotations

import importlib.util
import pathlib

from django.test import SimpleTestCase

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SCANNER = _REPO_ROOT / "scripts" / "verify_middleware_topology_parity.py"
_SETTINGS = _REPO_ROOT / "config" / "settings.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("_mw_parity", _SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MiddlewareTopologyParityTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.scanner = _load_scanner()
        cls.base, cls.tenants = cls.scanner.collect(_SETTINGS)

    def test_both_lists_parse(self):
        # If settings.py is restructured so either list stops parsing, every other
        # assertion here would vacuously pass. Fail loudly instead.
        self.assertGreater(len(self.base), 50, "base MIDDLEWARE failed to parse")
        self.assertGreater(len(self.tenants), 50, "tenants MIDDLEWARE failed to parse")

    def test_no_unclassified_topology_drift(self):
        tenant_set = set(self.tenants)
        classified = (
            set(self.scanner.INTENTIONAL_BASE_ONLY)
            | set(self.scanner.DO_NOT_ADD)
            | set(self.scanner.KNOWN_GAPS)
        )
        unclassified = [m for m in self.base if m not in tenant_set and m not in classified]
        self.assertEqual(
            unclassified,
            [],
            "These middleware are in the base MIDDLEWARE but NOT in the tenants list, "
            "so they never load in production (which takes the USE_DJANGO_TENANTS "
            "branch). Wire each into the tenants list in config/settings.py, or "
            "classify it in scripts/verify_middleware_topology_parity.py as "
            "INTENTIONAL_BASE_ONLY / DO_NOT_ADD / KNOWN_GAPS — with a reason verified "
            "against the code, not inferred from the name.",
        )

    def test_do_not_add_middleware_stay_out_of_prod(self):
        # These are base-only ON PURPOSE. Wiring one is a regression, not a fix:
        # RequestTimeoutMiddleware would run the chain in a ThreadPoolExecutor whose
        # thread-local DB connection has no search_path (every tenant query hits the
        # PUBLIC schema); TenantCorsAllowlistMiddleware permanently mutates the global
        # CORS_ALLOWED_ORIGINS and would leak one tenant's origins to the next request.
        tenant_set = set(self.tenants)
        wired = [m for m in self.scanner.DO_NOT_ADD if m in tenant_set]
        self.assertEqual(
            wired,
            [],
            "DO_NOT_ADD middleware are wired into the tenants (production) list. Read "
            "the reason in the scanner before assuming this was a fix — these cause "
            "tenant-isolation breaches, cross-tenant leaks, or are dead code.",
        )

    def test_tiers_do_not_overlap(self):
        # An entry in two tiers means two contradictory verdicts; the gate would then
        # depend on dict iteration order rather than on a decision anyone made.
        tiers = {
            "INTENTIONAL_BASE_ONLY": set(self.scanner.INTENTIONAL_BASE_ONLY),
            "DO_NOT_ADD": set(self.scanner.DO_NOT_ADD),
            "KNOWN_GAPS": set(self.scanner.KNOWN_GAPS),
        }
        names = list(tiers)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                with self.subTest(pair=(names[i], names[j])):
                    self.assertEqual(tiers[names[i]] & tiers[names[j]], set())

    def test_no_phantom_classifications(self):
        # A classified middleware that is no longer in the base list is stale bookkeeping:
        # it makes the tier counts lie and hides that the entry is gone.
        classified = (
            set(self.scanner.INTENTIONAL_BASE_ONLY)
            | set(self.scanner.DO_NOT_ADD)
            | set(self.scanner.KNOWN_GAPS)
        )
        phantom = sorted(classified - set(self.base))
        self.assertEqual(
            phantom,
            [],
            "These are classified in the scanner but no longer appear in the base "
            "MIDDLEWARE. Delete the stale entries.",
        )

    def test_known_gaps_only_shrink(self):
        tenant_set = set(self.tenants)
        stale = [m for m in self.scanner.KNOWN_GAPS if m in tenant_set]
        self.assertEqual(
            stale,
            [],
            "These are listed as KNOWN_GAPS but are now wired into the tenants list. "
            "Delete them from KNOWN_GAPS so the list can only shrink.",
        )

    def test_billing_enforcement_middleware_load_in_prod(self):
        # The specific regressions this module was written for. These are revenue
        # controls: without them prod cannot 402 a delinquent tenant's finance
        # writes, and cannot meter the billable db_sessions dimension at all.
        tenant_set = set(self.tenants)
        for dotted in (
            "apps.finance.subscription_gate.FinanceSubscriptionGateMiddleware",
            "apps.billing.middleware_metering.DBSessionMeteringMiddleware",
        ):
            with self.subTest(middleware=dotted):
                self.assertIn(
                    dotted,
                    tenant_set,
                    f"{dotted} is absent from the tenants MIDDLEWARE, so it does not "
                    "run in production.",
                )

    def test_intentional_base_only_entries_carry_a_reason(self):
        for dotted, reason in self.scanner.INTENTIONAL_BASE_ONLY.items():
            with self.subTest(middleware=dotted):
                self.assertTrue(
                    reason and reason.strip(),
                    f"{dotted} is classified INTENTIONAL_BASE_ONLY with no reason.",
                )
