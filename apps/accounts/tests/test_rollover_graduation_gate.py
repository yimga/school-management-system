"""W22 graduation-requirements gate on the rollover apply path.

Marking ``RolloverProposalItem.is_graduate`` graduates a student irreversibly
(status → ALUMNI, dropped from the active roll). This suite proves the apply
engine ``_apply_rollover_proposal_impl`` now verifies the school's CONFIGURED
graduation requirements first:

* an off-track graduate is NOT graduated and is counted when
  ``override_graduation_gate=False`` (mirrors the outstanding-returns skip);
* the same graduate IS graduated when ``override_graduation_gate=True``;
* an eligible graduate graduates normally;
* with NO requirements configured, graduation proceeds exactly as before
  (behaviour-preserving regression guard).

MUST-FIRE: every test calls the impl with the new ``override_graduation_gate``
kwarg, which does not exist on the pre-change signature (TypeError), and test 1
additionally asserts the off-track student is left un-graduated — impossible
before the gate existed. The backup gate is satisfied here with
``override_backup_gate=True`` so these tests isolate the graduation gate.

Scores use the francophone /20 operational scale (bare-school default), where a
16 is a passing mark (pass = half the scale).
"""

from django.test import TestCase

from apps.accounts.models import RolloverProposal, RolloverProposalItem, User
from apps.accounts.tasks import _apply_rollover_proposal_impl
from apps.people.models import StudentProfile
from apps.people.tests.test_enrollment import EnrollmentFixtureMixin


class RolloverGraduationGateTests(EnrollmentFixtureMixin, TestCase):
    def setUp(self):
        self.build_school("grad-gate")
        self.actor = User.objects.create_user(
            username="grad-gate-approver",
            password="pass12345",
            role=User.Role.ADMIN,
        )

    def _set_requirements(self, **reqs):
        settings = dict(getattr(self.school, "settings", None) or {})
        settings["graduation_requirements"] = reqs
        self.school.settings = settings
        self.school.save(update_fields=["settings"])

    def _graduate_proposal(self, student):
        proposal = RolloverProposal.objects.create(
            school=self.school,
            source_year=self.year_1,
            target_year=self.year_2,
            status=RolloverProposal.Status.APPROVED,
            created_by=self.actor,
            approved_by=self.actor,
        )
        RolloverProposalItem.objects.create(
            proposal=proposal,
            student=student,
            current_classroom_id=self.grade5_y1.pk,
            is_graduate=True,
        )
        return proposal

    def test_ineligible_graduate_blocked_without_override(self):
        self._set_requirements(min_subjects_passed=1)
        student = self.make_student("GG-FAIL")  # no marks → zero subjects passed
        proposal = self._graduate_proposal(student)

        result = _apply_rollover_proposal_impl(
            proposal.id, override_backup_gate=True, override_graduation_gate=False
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["graduation_blocked"], 1, result)
        self.assertEqual(result["graduated"], 0, result)
        self.assertIn(student.pk, result["blocked_graduates"])

        student.refresh_from_db()
        self.assertNotEqual(student.status, StudentProfile.Status.ALUMNI)
        self.assertTrue(student.is_active)

    def test_ineligible_graduate_graduates_with_override(self):
        self._set_requirements(min_subjects_passed=1)
        student = self.make_student("GG-OVERRIDE")  # off-track
        proposal = self._graduate_proposal(student)

        result = _apply_rollover_proposal_impl(
            proposal.id, override_backup_gate=True, override_graduation_gate=True
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["graduation_blocked"], 0, result)
        self.assertEqual(result["graduated"], 1, result)

        student.refresh_from_db()
        self.assertEqual(student.status, StudentProfile.Status.ALUMNI)
        self.assertFalse(student.is_active)

    def test_eligible_graduate_graduates_normally(self):
        self._set_requirements(min_subjects_passed=1)
        student = self.make_student("GG-PASS")
        self.score(student, 16, 15, 17)  # one passing subject
        proposal = self._graduate_proposal(student)

        result = _apply_rollover_proposal_impl(
            proposal.id, override_backup_gate=True, override_graduation_gate=False
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["graduation_blocked"], 0, result)
        self.assertEqual(result["graduated"], 1, result)

        student.refresh_from_db()
        self.assertEqual(student.status, StudentProfile.Status.ALUMNI)

    def test_no_requirements_configured_graduates_as_today(self):
        # No graduation_requirements on the school → the gate must be inert, so an
        # otherwise-off-track student graduates exactly as before this change.
        student = self.make_student("GG-NOCFG")  # no marks, but no config either
        proposal = self._graduate_proposal(student)

        result = _apply_rollover_proposal_impl(
            proposal.id, override_backup_gate=True, override_graduation_gate=False
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["graduation_blocked"], 0, result)
        self.assertEqual(result["graduated"], 1, result)

        student.refresh_from_db()
        self.assertEqual(student.status, StudentProfile.Status.ALUMNI)
