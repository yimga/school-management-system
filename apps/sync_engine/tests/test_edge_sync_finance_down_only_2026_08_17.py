"""Edge parity Slice 6 — finance rides the rail DOWN-ONLY and DELIBERATELY PARTIAL.

Only ``finance.Invoice`` joins: the box learns what a family OWES so a bursar can work
through an outage, and the protected ``invoice`` policy means it can never push a money
change back up — that raises a Sync Center conflict instead.

``finance.Payment`` and ``finance.PaymentProofUpload`` are HELD OUT on purpose (see
``docs/EDGE_SYNC_FINANCE_HOLD.md``). Two independent reasons, both asserted below so the
hold is enforced rather than merely written down:

  1. Neither carries an ``updated_at`` column at all, so the incremental delta cannot even
     query them (``filter(updated_at__gt=since)`` raises FieldError). Adding ``auto_now``
     to the money ledger changes write behaviour on the platform's most sensitive tables.
  2. ``Payment`` holds live settlement state, and POLICIES already declares
     ``payment_settlement`` ONLINE_REQUIRED — a charge against a gateway is a live
     transaction, never an offline-replayable one.

``test_held_out_money_models_still_lack_the_delta_cursor`` is a REVISIT TRIGGER: if
someone later adds ``updated_at`` to those tables, it fails — forcing a conscious decision
about registering them instead of letting the hold quietly rot.
"""
from __future__ import annotations

import datetime as dt
import uuid
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.accounts.models import User
from apps.api.sync_services import (
    _LWW_SAFE_ENTITIES,
    _conflict_decision,
    _get_entity_config,
    _insert_fk_targets,
    _sync_conflict_policy,
    apply_changes,
)
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_inbox import apply_pulled_bundle
from apps.sync_engine.edge_outbox import build_edge_delta_bundle
from apps.sync_engine.policy_registry import POLICIES, MergeStrategy, normalize_entity

_SIGN_KEY = "edge-finance-test-key"
_ENTITY = "invoice"


class InvoiceRegistrationTests(TestCase):
    def test_invoice_registered_without_its_file_fields(self):
        cfg = _get_entity_config(include_derived=True)
        self.assertIn(_ENTITY, cfg)
        _model, fields = cfg[_ENTITY]
        # The amounts ride (down) so the box can show what is owed.
        self.assertIn("total_amount", fields)
        self.assertIn("balance_amount", fields)
        self.assertIn("status", fields)
        # The bundle carries no file BYTES, so a stored path must never ride.
        self.assertNotIn("attachment", fields)
        self.assertNotIn("payment_proof", fields)
        self.assertNotIn("school", fields)
        self.assertNotIn("client_offline_id", fields)

    def test_invoice_policy_is_declared_explicitly_not_fail_closed(self):
        self.assertIn(
            normalize_entity(_ENTITY),
            POLICIES,
            "money must carry a DECLARED policy, not rely on get_policy's fail-closed default",
        )
        strategy, protected = _sync_conflict_policy(_ENTITY)
        self.assertTrue(protected)
        self.assertEqual(strategy, MergeStrategy.MANUAL_REVIEW)
        self.assertNotIn(_ENTITY, _LWW_SAFE_ENTITIES)

    def test_direction_matrix_is_down_only(self):
        newer = timezone.now()
        older = newer - dt.timedelta(days=1)
        self.assertEqual(_conflict_decision(_ENTITY, "cloud-pull", newer, older), "apply")
        self.assertEqual(_conflict_decision(_ENTITY, "edge-push", newer, older), "conflict")
        self.assertEqual(_conflict_decision(_ENTITY, None, newer, older), "conflict")

    def test_fk_remap_reaches_student(self):
        targets = _insert_fk_targets(_get_entity_config(include_derived=True)).get(_ENTITY)
        self.assertEqual(targets.get("student_id"), "student")

    def test_payment_and_proof_are_not_on_the_rail(self):
        cfg = _get_entity_config(include_derived=True)
        for held in ("payment", "fee_payment", "payment_proof_upload", "payment_proof"):
            self.assertNotIn(held, cfg, f"{held} must not ride until the hold is resolved")

    def test_held_out_money_models_still_lack_the_delta_cursor(self):
        """REVISIT TRIGGER — fails if updated_at is ever added to these tables."""
        from apps.finance.models import Payment, PaymentProofUpload

        for model in (Payment, PaymentProofUpload):
            names = {f.name for f in model._meta.get_fields()}
            self.assertNotIn(
                "updated_at",
                names,
                f"{model.__name__} gained an updated_at cursor — the edge-sync finance hold "
                f"(docs/EDGE_SYNC_FINANCE_HOLD.md) must be re-evaluated, not left in place "
                f"by default",
            )

    def test_payment_settlement_is_declared_online_required(self):
        """The second, independent reason Payment is held out."""
        self.assertEqual(
            POLICIES["payment_settlement"].strategy, MergeStrategy.ONLINE_REQUIRED
        )


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class InvoiceDownOnlyRoundTripTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Fin {uid}", slug=f"fin-{uid}", subdomain=f"fin{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"fin_admin_{uid}", password="Test1234", email=f"f{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name=f"2026/2027-{uid}",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
        )
        self.dept = Department.objects.create(school=self.school, name="Gen", code=f"G-{uid}")
        self.spec = Specialty.objects.create(
            school=self.school, department=self.dept, name="Gen", code=f"GS-{uid}"
        )
        self.classroom = Classroom.objects.create(
            school=self.school, academic_year=self.year, department=self.dept,
            name="Form 1", code=f"F1-{uid}",
        )
        self.profile = ComplianceProfile.objects.create(name=f"CP {uid}", country_code="CM")
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Jae", last_name="Learner",
            student_code=f"STD-{uid}", admission_number=f"ADM-{uid}",
            academic_year=self.year, classroom=self.classroom, specialty=self.spec,
        )

    def _invoice(self, total="100.00"):
        return Invoice.objects.create(
            school=self.school,
            profile=self.profile,
            academic_year=self.year,
            student=self.student,
            total_amount=Decimal(total),
            balance_amount=Decimal(total),
        )

    def test_cloud_pull_lands_the_cloud_amount_on_the_box(self):
        inv = self._invoice(total="100.00")
        data, _meta = build_edge_delta_bundle(self.school, since=None, entities=[_ENTITY])
        rows, errors = verify_and_parse_bundle(data, expected_school_id=self.school.id)
        self.assertFalse(errors, errors)
        self.assertTrue(any(r["id"] == inv.pk for r in rows if r["entity_type"] == _ENTITY))

        old = timezone.now() - timezone.timedelta(days=1)
        Invoice.objects.filter(pk=inv.pk).update(
            total_amount=Decimal("5.00"), balance_amount=Decimal("5.00"), updated_at=old
        )
        result = apply_pulled_bundle(self.school, self.user, data, origin="cloud-pull")
        self.assertTrue(result["ok"], result)
        inv.refresh_from_db()
        self.assertEqual(inv.total_amount, Decimal("100.00"))

    def test_box_push_cannot_move_money_and_the_conflict_is_reviewable(self):
        """Also proves the Decimal conflict-snapshot fix holds for MONEY, not just grades:
        an unencodable snapshot used to make the conflict record itself fail to save, so
        the row was neither applied NOR reviewable."""
        inv = self._invoice(total="100.00")
        rows = [
            {
                "entity_type": _ENTITY,
                "id": inv.pk,
                "changes": {"total_amount": "1.00", "balance_amount": "1.00"},
                "updated_at": (timezone.now() + dt.timedelta(days=1)).isoformat(),
            }
        ]
        out = apply_changes(
            str(self.school.id), self.user, rows, persist_conflicts=True, sync_origin="edge-push"
        )
        self.assertEqual(out["success_count"], 0, out)
        self.assertEqual(len(out["conflicts"]), 1, out)
        self.assertEqual(out["results"][0]["status"], 409, out)
        self.assertIsNotNone(out["results"][0].get("conflict_id"), out)
        inv.refresh_from_db()
        self.assertEqual(
            inv.total_amount, Decimal("100.00"), "a box push rewrote an invoice amount"
        )
