"""Every safeguarding transition must leave a CRITICAL audit row.

``apps/safeguarding/README.md`` states it as an invariant, not a preference:

    Every transition writes exactly one ``CRITICAL``-sensitivity audit row. This
    is a safeguarding audit invariant, not a logging preference.

The kernel upholds its half -- ``create_concern`` and ``transition_concern`` each
return a fully-populated ``AuditRow`` whose docstring says it mirrors
``apps.compliance.models_audit.AuditLog``. The service layer then dropped every one
of them on the floor: ``entry, _audit = create_concern(...)``,
``entry, _audit2 = transition_concern(...)``, and a third in
``acknowledge_and_transition``. Nothing else in the app writes an AuditLog.

So a child-protection disclosure could be raised, acknowledged, escalated to a
statutory referral and closed, and the compliance audit trail would show nothing at
all -- while the README promised a CRITICAL row per step and the kernel tests
proved the rows were correctly *built*.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.compliance.models_audit import AuditLog
from apps.safeguarding.concern_kernel import ACKNOWLEDGED, SUBMITTED
from apps.safeguarding.services import (
    acknowledge_and_transition,
    submit_concern_for_school,
)
from apps.schools.models import School, SchoolMembership


class ConcernAuditRowsArePersistedTests(TestCase):
    def setUp(self):
        slug = f"sgaud-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Audit School", slug=slug, subdomain=slug
        )
        self.reporter = User.objects.create_user(username=f"rep_{slug}", password="x")
        self.reporter.role = "TEACHER"
        self.reporter.save(update_fields=["role"])
        self.admin = User.objects.create_user(username=f"adm_{slug}", password="x")
        self.admin.role = "ADMIN"
        self.admin.save(update_fields=["role"])
        SchoolMembership.objects.create(
            user=self.reporter, school=self.school, role="TEACHER"
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN"
        )

    def _rows(self):
        return AuditLog.objects.filter(app_label="safeguarding").order_by("pk")

    def _submit(self):
        return submit_concern_for_school(
            school=self.school,
            reporter_user_id=self.reporter.pk,
            # A real key from the kernel registry. The safeguarding WIZARD offers a
            # completely disjoint vocabulary ("abuse_disclosure" and friends), which
            # get_category() cannot resolve -- tracked separately.
            category_key="physical_abuse",
            narrative="Disclosed at pickup; no contact details recorded here.",
        )

    def test_submitting_a_concern_records_its_creation_and_its_transition(self):
        self.assertEqual(self._rows().count(), 0, "fixture must start clean")
        entry = self._submit()

        rows = list(self._rows())
        self.assertEqual(
            len(rows),
            2,
            "create_concern and the DRAFT->SUBMITTED transition each return an "
            f"AuditRow; both must be persisted. Got: {[r.reason for r in rows]}",
        )
        self.assertEqual([r.action for r in rows], ["CREATE", "UPDATE"])
        for row in rows:
            self.assertEqual(row.sensitivity, "CRITICAL")
            self.assertEqual(row.model_name, "SafeguardingConcern")
            self.assertEqual(row.object_id, entry.concern_id)
            self.assertEqual(row.user_id, self.reporter.pk)

    def test_the_transition_row_names_the_stage_it_moved_to(self):
        """A row that cannot say what changed is not an audit trail."""
        self._submit()
        transition = self._rows().filter(action="UPDATE").first()
        self.assertIsNotNone(transition)
        self.assertIn(SUBMITTED, transition.reason)
        self.assertEqual(transition.new_values.get("stage_to"), SUBMITTED)

    def test_acknowledging_records_the_actor_who_did_it(self):
        entry = self._submit()
        before = self._rows().count()

        acknowledge_and_transition(
            school=self.school,
            concern_id=entry.concern_id,
            actor_user_id=self.admin.pk,
            target_stage=ACKNOWLEDGED,
        )

        rows = list(self._rows())
        self.assertEqual(len(rows), before + 1, "the acknowledgement was not audited")
        latest = rows[-1]
        self.assertEqual(latest.sensitivity, "CRITICAL")
        self.assertEqual(
            latest.user_id,
            self.admin.pk,
            "the audit row must name the person who acknowledged, not the reporter",
        )
        self.assertEqual(latest.new_values.get("stage_to"), ACKNOWLEDGED)

    def test_the_narrative_itself_is_never_written_into_the_audit_row(self):
        """The row keeps the shape of the disclosure, never its contents."""
        entry = self._submit()
        for row in self._rows():
            blob = f"{row.new_values} {row.old_values} {row.reason} {row.object_repr}"
            self.assertNotIn("pickup", blob.lower(), blob)
        self.assertTrue(entry.concern_id)
