"""S4 (Workflow engine) — orchestration runners import models that exist.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 fix. Three concrete runners in apps/orchestration/runners.py
imported models that do not resolve, and the import sat inside a try/except whose
``_ORCHESTRATION_STEP_QUERY_ERRORS`` tuple INCLUDES ImportError — so each failed
import was silently swallowed and the runner's reported work-count was pinned to 0
forever (the WF4 silent-zeroing pattern):
  * FeeFollowUpRunner   -> apps.finance.models.InvoiceReminder   (no such model)
  * AdmissionsRunner    -> apps.requests.models.AdmissionApplication (no such model)
  * ReEnrollmentRunner  -> apps.accounts.models.StudentProfile   (lives in apps.people)

Fixed to the real models: finance.PaymentReminder, people.Applicant (stage-based),
people.StudentProfile. This test proves the models resolve AND the exact field
lookups each runner uses are valid (queryset compiles).
"""

from __future__ import annotations

import os
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


class RunnerModelSourceTests(unittest.TestCase):

    def test_fee_followup_uses_real_payment_reminder(self) -> None:
        from apps.finance.models import PaymentReminder

        q = PaymentReminder.objects.filter(
            invoice__school_id=1, is_active=True
        )
        # .query renders the SQL → raises FieldError if a lookup is invalid.
        self.assertTrue(str(q.query))

    def test_admissions_uses_real_applicant_stage(self) -> None:
        from apps.people.models import Applicant

        self.assertTrue(hasattr(Applicant.Stage, "APPLIED"))
        self.assertTrue(hasattr(Applicant.Stage, "UNDER_REVIEW"))
        q = Applicant.objects.filter(
            school_id=1,
            stage__in=[Applicant.Stage.APPLIED, Applicant.Stage.UNDER_REVIEW],
        )
        self.assertTrue(str(q.query))

    def test_reenrollment_uses_people_student_profile(self) -> None:
        from apps.people.models import StudentProfile

        q = StudentProfile.objects.filter(school_id=1, is_active=True)
        self.assertTrue(str(q.query))

    def test_dead_model_names_are_gone_from_runners(self) -> None:
        from pathlib import Path

        repo = Path(__file__).resolve().parent.parent.parent.parent
        src = (repo / "apps" / "orchestration" / "runners.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertNotIn("import InvoiceReminder", src)
        self.assertNotIn("AdmissionApplication", src)
        self.assertNotIn("from apps.accounts.models import StudentProfile", src)


if __name__ == "__main__":
    unittest.main()
