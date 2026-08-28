"""Autopilot must not close a row on a class it guessed (2026-08-28).

`orchestrator.py` records `reason_source` on every held row -- `declared` when
the lander named the class, `fallback` when `classify_message` guessed it from
the error text -- and its own comment states the contract:

    a remediation pass must be able to tell a class the lander asserted from one
    a matcher guessed, and to refuse to act automatically on a guess

Nothing consulted it. Four of the five autopilot rules can live with that,
because they re-read the source row and decide from what is in it -- the class
is a pre-filter, not the evidence. `auto_dismiss_informational` cannot: it
closes the row on the strength of the class alone, without looking at the row,
on the grounds that `source_deletion` and `duplicate` mean "already handled".

What that cost, measured on this tree:

* **No lander declares `DUPLICATE`.** Zero sites. So every row that reaches that
  class got there through `classify_message`, whose whole rule is
  ``"duplicate" in e or "unique" in e or "already exists" in e``.
* That matches a real write FAILURE. `UNIQUE constraint failed:
  finance_invoice.reference` is a row that did **not** land, and it was being
  closed as though it had -- the data dropped, the queue reporting success.

`SOURCE_DELETION` is declared at two sites (academics, sections) and keeps
clearing automatically, which is the case the rule was written for.

A held row whose payload predates `reason_source` reads as `fallback` and stays
held. That is the correct direction for a rule about doubt.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.auto_remediate import (
    auto_dismiss_informational,
    preview_autopilot_decisions,
)
from apps.migration_cloud.landers.reason_codes import (
    NO_ACTION_REASON_CODES,
    classify_message,
)
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.schools.models import School, SchoolMembership

User = get_user_model()

# Real strings a lander or the database produces for a row that did NOT land.
FAILED_WRITE_MESSAGES = [
    "UNIQUE constraint failed: finance_invoice.reference",
    'duplicate key value violates unique constraint "people_studentprofile_ext_key"',
    "admission number must be unique within the school",
    "a staff member with this email already exists",
]


class TheMatcherCallsAFailedWriteADuplicateTests(TestCase):
    """The premise. If this stops holding, the rule below can be relaxed."""

    def test_a_unique_violation_is_guessed_as_needs_nobody(self):
        for message in FAILED_WRITE_MESSAGES:
            with self.subTest(message=message):
                self.assertIn(
                    classify_message(message),
                    NO_ACTION_REASON_CODES,
                    "premise changed -- the matcher no longer calls this needs-nobody",
                )

    def test_no_lander_declares_duplicate(self):
        # If a lander ever declares DUPLICATE deliberately, its rows become
        # auto-closable again and this fixture should be revisited.
        import pathlib

        landers = pathlib.Path("apps/migration_cloud/landers")
        declaring = [
            path.name
            for path in landers.glob("*_lander.py")
            if "reason_code=DUPLICATE" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(declaring, [], "a lander now declares DUPLICATE")


class NoActionDismissalRequiresADeclaredClassTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Declared Class School",
            slug="declared-class-school",
            subdomain="declared-class-school",
            is_active=True,
            is_approved=True,
        )
        self.admin = User.objects.create_user(
            username="declared-class-admin", password="x", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.bundle = MigrationBundle.objects.create(
            label="declared-class",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="declared-class-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def _hold(self, *, issue_class, error, reason_source, domain="finance"):
        payload = {"error": error, "artifact": "fees.csv", "source_row": {"ref": "INV-1"}}
        if reason_source is not None:
            payload["reason_source"] = reason_source
        return MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain=domain,
            row_index=1,
            issue_class=issue_class,
            payload=payload,
        )

    def _pending(self, rec) -> bool:
        rec.refresh_from_db()
        return rec.status == MigrationQuarantineRecord.Status.PENDING

    def test_a_guessed_duplicate_is_not_dismissed(self):
        rec = self._hold(
            issue_class="duplicate",
            error="UNIQUE constraint failed: finance_invoice.reference",
            reason_source="fallback",
        )
        result = auto_dismiss_informational(self.bundle, user=self.admin)
        self.assertEqual(result["dismissed"], 0)
        self.assertEqual(result["held_on_guessed_class"], 1)
        self.assertTrue(
            self._pending(rec),
            "a failed write was closed as an already-applied row",
        )

    def test_a_declared_source_deletion_still_clears(self):
        rec = self._hold(
            issue_class="source_deletion",
            error="the source marked this row deleted",
            reason_source="declared",
            domain="academics",
        )
        result = auto_dismiss_informational(self.bundle, user=self.admin)
        self.assertEqual(result["dismissed"], 1)
        self.assertFalse(self._pending(rec))

    def test_a_payload_predating_reason_source_is_held(self):
        rec = self._hold(
            issue_class="duplicate",
            error="already exists",
            reason_source=None,
        )
        auto_dismiss_informational(self.bundle, user=self.admin)
        self.assertTrue(
            self._pending(rec), "absent evidence must not read as declared"
        )

    def test_the_preview_reports_it_as_needing_a_person(self):
        self._hold(
            issue_class="duplicate",
            error="UNIQUE constraint failed: finance_invoice.reference",
            reason_source="fallback",
        )
        report = preview_autopilot_decisions(self.bundle)
        self.assertEqual(report["counts"]["needs_person"], 1)
        self.assertEqual(report["counts"]["auto_close"], 0)
        self.assertEqual(report["held_because_class_was_guessed"], 1)
        self.assertEqual(report["rows"][0]["rule"], "guessed_no_action")

    def test_preview_and_engine_still_agree(self):
        self._hold(
            issue_class="duplicate",
            error="already exists",
            reason_source="fallback",
        )
        declared = self._hold(
            issue_class="source_deletion",
            error="the source marked this row deleted",
            reason_source="declared",
            domain="academics",
        )
        predicted = preview_autopilot_decisions(self.bundle)
        will_close = {
            r["record_id"] for r in predicted["rows"] if r["outcome"] == "auto_close"
        }
        self.assertEqual(will_close, {declared.pk})

        auto_dismiss_informational(self.bundle, user=self.admin)

        still_pending = set(
            MigrationQuarantineRecord.objects.filter(
                migration_run=self.run,
                status=MigrationQuarantineRecord.Status.PENDING,
            ).values_list("pk", flat=True)
        )
        self.assertFalse(will_close & still_pending)
