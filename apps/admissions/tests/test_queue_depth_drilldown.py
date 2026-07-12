"""The admissions cockpit tile's drill-down params must be honored by the list.

The tile emits ``?stage=ACTIONABLE`` (a meta-stage) for its "Awaiting review"
total and ``?stage=<CODE>&stale=1`` for a stale-leads chip, but backend_applicant
_list only ever filtered on a real ``Applicant.Stage`` member and never read
``stale`` — so ACTIONABLE fell through to the WHOLE unfiltered list and the stale
chip dropped its staleness constraint. queue_depth now exposes the actionable set
and stale cutoff as one SOT, and the list view honors both.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from apps.admissions.queue_depth import actionable_stage_codes, stale_lead_cutoff


class QueueDepthSotHelpersTests(SimpleTestCase):
    def test_actionable_stage_codes_match_the_tile(self):
        self.assertEqual(
            set(actionable_stage_codes()), {"APPLIED", "UNDER_REVIEW", "ACCEPTED"}
        )
        # LEAD/REJECTED/ENROLLED are NOT awaiting-review work.
        for excluded in ("LEAD", "REJECTED", "ENROLLED"):
            self.assertNotIn(excluded, actionable_stage_codes())

    def test_stale_cutoff_is_fourteen_days_before_now(self):
        now = timezone.now()
        cutoff = stale_lead_cutoff(now=now)
        self.assertEqual((now - cutoff).days, 14)


class ApplicantListDrilldownTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import User
        from apps.people.models import Applicant
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        cls.school = School.objects.create(
            name=f"Adm {uid}", slug=f"adm-{uid}", subdomain=f"adm-{uid}"
        )
        cls.superuser = User.objects.create_superuser(
            username=f"su_{uid}", email="su@example.com", password="pw"
        )

        def mk(stage, tag, *, days_old=0):
            a = Applicant.objects.create(
                school=cls.school,
                first_name=tag,
                last_name="Test",
                email=f"{tag}@example.test",
                stage=stage,
            )
            if days_old:
                old = timezone.now() - timedelta(days=days_old)
                Applicant.objects.filter(pk=a.pk).update(created_at=old)
            return a

        cls.applied_fresh = mk("APPLIED", "applied-fresh")
        cls.applied_stale = mk("APPLIED", "applied-stale", days_old=30)
        cls.under_review = mk("UNDER_REVIEW", "under-review")
        cls.accepted = mk("ACCEPTED", "accepted")
        cls.lead = mk("LEAD", "lead")
        cls.rejected = mk("REJECTED", "rejected")
        cls.enrolled = mk("ENROLLED", "enrolled")

    def _csv(self, query):
        from apps.people import views_backend

        req = RequestFactory().get("/backend/applicants/?" + query + "&format=csv")
        req.user = self.superuser
        req.school = self.school
        resp = views_backend.backend_applicant_list(req)
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode("utf-8")

    def test_actionable_meta_stage_filters_to_actionable_set(self):
        body = self._csv("stage=ACTIONABLE")
        for present in ("applied-fresh", "applied-stale", "under-review", "accepted"):
            self.assertIn(f"{present}@example.test", body)
        for absent in ("lead", "rejected", "enrolled"):
            self.assertNotIn(f"{absent}@example.test", body)

    def test_stale_param_on_a_stage_filters_to_the_stale_subset(self):
        body = self._csv("stage=APPLIED&stale=1")
        self.assertIn("applied-stale@example.test", body)
        self.assertNotIn("applied-fresh@example.test", body)

    def test_stale_param_alone_filters_by_created_at(self):
        body = self._csv("stale=1")
        # Only the 30-day-old applicant is stale; every fresh one is excluded.
        self.assertIn("applied-stale@example.test", body)
        for fresh in ("applied-fresh", "under-review", "accepted", "lead"):
            self.assertNotIn(f"{fresh}@example.test", body)

    def test_real_stage_still_filters_exactly(self):
        body = self._csv("stage=LEAD")
        self.assertIn("lead@example.test", body)
        self.assertNotIn("applied-fresh@example.test", body)

    def test_unknown_stage_is_ignored_shows_all(self):
        # A junk stage that is neither ACTIONABLE nor a real member → no filter.
        body = self._csv("stage=BOGUS")
        for tag in ("applied-fresh", "lead", "enrolled"):
            self.assertIn(f"{tag}@example.test", body)
