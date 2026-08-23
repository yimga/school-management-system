"""One transaction can back several SLOs; every one of them must be observable.

``auth.login`` backs both a latency SLO and an availability SLO. While the
transaction index was one-to-one, the second registration was unreachable, so
``runmycampus_auth_login_availability_requests_total`` had no producer anywhere
in the tree and its generated burn-rate alert could never fire.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.observability import metrics as obs_metrics
from apps.observability.slo import SLOS
from apps.observability.slo_metrics import (
    TRANSACTION_TO_SLO,
    record_traced_transaction,
)


class MultiSloTransactionEmitTests(SimpleTestCase):
    def setUp(self) -> None:
        obs_metrics._reset_backend_cache()
        self.emitted: list[tuple[str, str, float]] = []

        def _counter(name: str, value: float = 1, *, labels=None, tags=None):
            self.emitted.append(("counter", name, float(value)))

        def _histogram(name: str, value: float, *, labels=None, tags=None, buckets=None):
            self.emitted.append(("histogram", name, float(value)))

        self._counter_patch = patch(
            "apps.observability.slo_metrics.emit_counter", side_effect=_counter
        )
        self._hist_patch = patch(
            "apps.observability.slo_metrics.emit_histogram", side_effect=_histogram
        )
        self._counter_patch.start()
        self._hist_patch.start()

    def tearDown(self) -> None:
        self._counter_patch.stop()
        self._hist_patch.stop()
        obs_metrics._reset_backend_cache()

    def _names(self) -> list[str]:
        return [name for _kind, name, _value in self.emitted]

    def test_failed_login_feeds_both_the_latency_and_availability_slos(self):
        record_traced_transaction("auth.login", success=False, duration_seconds=0.31)
        names = self._names()
        # Guard against the vacuous pass: if the transaction resolved to nothing
        # at all, `names` would be empty and every assertIn below would be
        # meaningless. The latency series proves the call reached the emitter.
        self.assertIn("auth_login_duration_seconds", names)
        self.assertIn("auth_login_availability_requests_total", names)
        self.assertIn("auth_login_availability_failures_total", names)

    def test_failed_payment_record_feeds_its_availability_slo(self):
        record_traced_transaction(
            "finance.payment.record", success=False, duration_seconds=1.2
        )
        names = self._names()
        self.assertIn("finance_payment_record_duration_seconds", names)
        self.assertIn("finance_payment_record_availability_requests_total", names)
        self.assertIn("finance_payment_record_availability_failures_total", names)

    def test_http_server_still_leaves_web_availability_to_the_middleware(self):
        """``http.server`` also backs api.public_config; only that one may emit.

        The HTTP middleware records web.availability itself — emitting it here
        too would double-count every request.
        """
        record_traced_transaction("http.server", success=True, duration_seconds=0.05)
        names = self._names()
        self.assertIn("api_public_config_duration_seconds", names)
        self.assertNotIn("web_availability_requests_total", names)


class EverySloIsReachableFromATransactionTests(SimpleTestCase):
    """The inverse assertion the emit-site script never made.

    ``scripts/verify_slo_metrics_emit_sites.py`` only checks that each required
    transaction maps to SOME key; it cannot see an SLO that lost a collision.
    """

    def test_no_registered_slo_is_shadowed_by_a_shared_transaction(self):
        reachable: set[str] = set()
        for keys in TRANSACTION_TO_SLO.values():
            if isinstance(keys, str):  # pre-fix shape
                reachable.add(keys)
            else:
                reachable.update(keys)
        unreachable = sorted(
            slo.key
            for slo in SLOS
            if slo.sentry_transactions and slo.key not in reachable
        )
        self.assertEqual(
            unreachable,
            [],
            "these SLOs declare a sentry transaction but nothing can ever emit "
            f"an observation for them: {unreachable}",
        )
