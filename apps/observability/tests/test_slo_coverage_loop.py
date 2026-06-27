"""#18 Observability — coverage loop for the genuinely-important flows that
were missing a (correct-kind) SLO.

Pure no-DB ``SimpleTestCase``. Asserts the SHAPE of each NEW SLO added in the
2026-06-26 wave against the same structural rules ``scripts/verify_slo_registry.py``
enforces (kind ∈ allowed set; target ∈ (0, 100); positive window_days; latency
kinds carry threshold_ms > 0; non-latency kinds DO NOT). Each new SLO closes a
real gap:

* ``auth.login.availability``           — login could be FAST yet error out;
  the existing ``auth.login`` is latency-only.
* ``finance.payment_record.availability`` — payment WRITE succeeding matters
  more than its p95; the existing ``finance.payment_record`` is latency-only.
* ``reports.report_card.render``        — report-card render had no SLO at all.
* ``sync.delta_apply.latency``          — sync apply had only a *freshness* SLO
  (``sync.conflict_pending``), never a latency one.
* ``healthz.freshness``                 — the health probe had no freshness SLO.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability.slo import (
    SLOS,
    SLOKind,
    get_slo,
    slo_commitments_for_display,
    slos_by_key,
)

# Mirrors scripts/verify_slo_registry.py::ALLOWED_KINDS / LATENCY_KINDS.
_ALLOWED_KINDS = {"availability", "latency_p95", "latency_p99", "freshness", "error_rate"}
_LATENCY_KINDS = {"latency_p95", "latency_p99"}

# The new flows this wave closes, with their expected kind.
_NEW_SLOS: dict[str, str] = {
    "auth.login.availability": "availability",
    "finance.payment_record.availability": "availability",
    "reports.report_card.render": "latency_p95",
    "sync.delta_apply.latency": "latency_p95",
    "healthz.freshness": "freshness",
}


class NewSloCoverageShapeTests(SimpleTestCase):
    def test_each_new_slo_is_registered_with_expected_kind(self):
        index = slos_by_key()
        for key, expected_kind in _NEW_SLOS.items():
            with self.subTest(slo=key):
                slo = index.get(key)
                self.assertIsNotNone(slo, f"missing newly-added SLO: {key}")
                self.assertEqual(slo.kind, expected_kind)

    def test_each_new_slo_satisfies_registry_structural_rules(self):
        for key in _NEW_SLOS:
            slo = get_slo(key)
            with self.subTest(slo=key):
                # 1 & 2: key/label/kind non-empty + kind allowed.
                self.assertTrue(slo.key)
                self.assertTrue(slo.label)
                self.assertIn(slo.kind, _ALLOWED_KINDS)
                # 3: target in the open interval (0, 100).
                self.assertGreater(slo.target, 0)
                self.assertLess(slo.target, 100)
                # 4: positive int window.
                self.assertIsInstance(slo.window_days, int)
                self.assertGreater(slo.window_days, 0)
                # 5 & 6: latency kinds carry threshold_ms > 0; others do not.
                if slo.kind in _LATENCY_KINDS:
                    self.assertIsNotNone(
                        slo.threshold_ms, f"{key} latency SLO missing threshold_ms"
                    )
                    self.assertGreater(slo.threshold_ms, 0)
                else:
                    self.assertIsNone(
                        slo.threshold_ms,
                        f"{key} ({slo.kind}) must not carry threshold_ms",
                    )
                # 8: sentry_transactions is a tuple of strings.
                self.assertIsInstance(slo.sentry_transactions, tuple)
                for txn in slo.sentry_transactions:
                    self.assertIsInstance(txn, str)

    def test_new_keys_are_unique_and_not_shadowing_existing(self):
        # Belt-and-suspenders on rule 7 (unique keys) for the whole registry.
        all_keys = [s.key for s in SLOS]
        self.assertEqual(
            len(all_keys), len(set(all_keys)), "duplicate SLO key in registry"
        )
        for key in _NEW_SLOS:
            self.assertEqual(all_keys.count(key), 1, f"{key} is not unique")

    def test_kind_is_a_valid_slokind_literal(self):
        # The annotated Literal must still admit each new kind (guards a typo
        # like "latency_95" that the dataclass would happily accept at runtime).
        valid = set(SLOKind.__args__)  # type: ignore[attr-defined]
        for key, expected_kind in _NEW_SLOS.items():
            with self.subTest(slo=key):
                self.assertIn(expected_kind, valid)


class NewSloIntentTests(SimpleTestCase):
    """The new SLOs close a *distinct* concern, not a duplicate of an existing one."""

    def test_login_availability_is_distinct_from_login_latency(self):
        avail = get_slo("auth.login.availability")
        latency = get_slo("auth.login")
        self.assertEqual(avail.kind, "availability")
        self.assertEqual(latency.kind, "latency_p95")
        # Both reference the same Sentry transaction (availability vs p95 of it).
        self.assertIn("auth.login", latency.sentry_transactions)
        self.assertIn("auth.login", avail.sentry_transactions)

    def test_payment_availability_is_distinct_from_payment_latency(self):
        avail = get_slo("finance.payment_record.availability")
        latency = get_slo("finance.payment_record")
        self.assertEqual(avail.kind, "availability")
        self.assertEqual(latency.kind, "latency_p95")

    def test_sync_latency_is_distinct_from_sync_freshness(self):
        latency = get_slo("sync.delta_apply.latency")
        freshness = get_slo("sync.conflict_pending")
        self.assertEqual(latency.kind, "latency_p95")
        self.assertEqual(freshness.kind, "freshness")
        # Same underlying transaction, different objective.
        self.assertIn("sync.delta_apply", latency.sentry_transactions)
        self.assertIn("sync.delta_apply", freshness.sentry_transactions)

    def test_report_card_render_is_a_new_flow(self):
        slo = get_slo("reports.report_card.render")
        self.assertEqual(slo.kind, "latency_p95")
        self.assertGreater(slo.threshold_ms, 0)

    def test_healthz_freshness_present(self):
        slo = get_slo("healthz.freshness")
        self.assertEqual(slo.kind, "freshness")
        self.assertIsNone(slo.threshold_ms)

    def test_new_slos_flow_through_status_page_commitments(self):
        # The public status page derives rows from the registry; the new SLOs
        # must appear there with a human objective and no live-measurement leak.
        rows = {r["key"]: r for r in slo_commitments_for_display()}
        forbidden = {"current", "actual", "measured", "value", "status"}
        for key in _NEW_SLOS:
            with self.subTest(slo=key):
                self.assertIn(key, rows)
                self.assertTrue(rows[key]["objective"])
                self.assertFalse(forbidden & set(rows[key]))
