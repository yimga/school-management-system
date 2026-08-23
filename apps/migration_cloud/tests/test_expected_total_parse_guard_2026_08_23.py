"""An unparseable control total must never look like a passing guardrail.

``MigrationCloudExpectedTotalsView`` stored whatever the operator POSTed
(``cleaned[key[:64]] = str(value)[:64]``) and echoed it back in a 200, so the
figure read as accepted. ``evaluate_expected_totals`` then did
``if exp is None: continue`` — the key vanished from the report, ``checks`` came
back empty, ``GuardrailReport.ok`` was True and ``enforce_financial_guardrail``
returned without raising, so the bundle flipped to APPLIED.

The same typo also killed the fallback: ``orchestrator._maybe_check_financial_
guardrail`` short-circuits ``_handle_unverified_finance`` whenever
``bundle.expected_totals`` is truthy, and a dict holding an unreadable string IS
truthy. One mistyped total disabled the guardrail AND the "money landed
unverified" warning at once.

``_to_decimal`` only strips commas and ``$``, so a space-grouped figure — the
standard fr-FR presentation across this product's Francophone-Africa market —
is exactly such a typo: ``Decimal("1 250 00000")`` is InvalidOperation.

Now: the write boundary rejects it with a 400 naming the offending keys, and the
evaluator records a FAILED check instead of dropping the key, so the apply is
blocked either way.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.migration_cloud.guardrails import (
    enforce_financial_guardrail,
    evaluate_expected_totals,
)
from apps.migration_cloud.models import (
    BundleStatus,
    FinancialMismatchError,
    IntakeMethod,
    MigrationBundle,
)
from apps.migration_cloud.views import MigrationCloudExpectedTotalsView
from apps.schools.models import School

User = get_user_model()

KEY = "finance.invoice_total_amount"
FR_TOTAL = "1 250 000,00"  # space-grouped: what an fr-FR operator types


class _Base(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Guardrail Parse", slug="guardrail-parse",
            subdomain="guardrail-parse", is_active=True, is_approved=True,
        )

    def _bundle(self, key, **over):
        kwargs = {
            "label": key,
            "intake_method": IntakeMethod.FILE_UPLOAD,
            "idempotency_key": f"parse-{key}",
            "status": BundleStatus.APPLIED,
            "school": self.school,
            "expected_totals": {},
        }
        kwargs.update(over)
        return MigrationBundle.objects.create(**kwargs)


class UnparseableExpectedTotalTests(_Base):
    def test_parseable_total_still_passes(self):
        # Vacuity guard for the test below: identical shape, a readable figure —
        # proves the observed/tolerance plumbing agrees, so the failure below is
        # the unreadable expected value and nothing else.
        bundle = self._bundle("ok", expected_totals={KEY: "1250000.00"})
        report = evaluate_expected_totals(
            bundle=bundle, observed={KEY: "1250000.00"}
        )
        self.assertEqual(len(report.checks), 1)
        self.assertTrue(report.ok, report.to_dict())

    def test_unparseable_total_is_a_failed_check_not_a_dropped_one(self):
        bundle = self._bundle("bad", expected_totals={KEY: FR_TOTAL})
        report = evaluate_expected_totals(
            bundle=bundle, observed={KEY: "1250000.00"}
        )
        self.assertEqual(
            [c.key for c in report.checks], [KEY],
            "the unreadable expected total vanished from the report",
        )
        self.assertFalse(report.ok, report.to_dict())
        self.assertEqual([c.key for c in report.failed], [KEY])

    def test_enforce_refuses_a_bundle_carrying_an_unreadable_total(self):
        bundle = self._bundle("enforce", expected_totals={KEY: FR_TOTAL})
        with self.assertRaises(FinancialMismatchError):
            enforce_financial_guardrail(bundle=bundle)


class ExpectedTotalsWriteBoundaryTests(_Base):
    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()
        self.operator = User.objects.create_user(
            username="totals_operator", password="pass123", is_staff=True
        )

    def _post(self, bundle, payload):
        request = self.rf.post(
            f"/super/migration-cloud/bundles/{bundle.pk}/expected-totals/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.user = self.operator
        return MigrationCloudExpectedTotalsView.as_view()(
            request, bundle_id=bundle.pk, shell="super"
        )

    def test_a_readable_total_is_accepted_and_stored(self):
        bundle = self._bundle("write-ok")
        response = self._post(bundle, {KEY: "1250000.00"})
        self.assertEqual(response.status_code, 200, response.content)
        bundle.refresh_from_db()
        self.assertEqual(bundle.expected_totals, {KEY: "1250000.00"})

    def test_an_unreadable_total_is_refused_and_not_stored(self):
        bundle = self._bundle("write-bad")
        response = self._post(bundle, {KEY: FR_TOTAL, "finance.invoice_count": "12"})
        self.assertEqual(response.status_code, 400, response.content)
        body = json.loads(response.content)
        self.assertIn(KEY, json.dumps(body))
        bundle.refresh_from_db()
        # Nothing was stored — not the bad key, and not the good one either, so
        # the operator cannot end up with a half-applied set of control totals.
        self.assertEqual(bundle.expected_totals, {})
