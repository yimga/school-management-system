"""Review-open autopilot mutates on a GET, so it must not fire on a fetch (2026-08-28).

Opening the held-review page now runs zero-touch triage and CLOSES held rows.
That makes it a state-changing GET, and CSRF protection does not reach a GET --
Django cannot require a token for one, and browsers send cookies with every
sub-resource request. So a third-party page carrying

    <img src="https://<tenant>/portal/configure/migration/8/review/">

would run the triage as whoever is signed in, on a bundle they never opened; a
link prefetch would do the same for a page nobody visited. Neither leaves a
trace distinguishable from a real page open -- the audit event records the
victim as the actor.

The equivalent POST endpoint is CSRF-protected, so this was a new hole opened by
moving the same work onto the GET, not a pre-existing one.

Fetch-metadata (``Sec-Fetch-Dest`` / ``Sec-Purpose``) is sent by every browser
capable of mounting either attack, and a real navigation always carries
``Sec-Fetch-Dest: document``. A client that sends no fetch-metadata at all --
curl, the Django test client, an old browser -- is still allowed through, on
purpose: the point is to remove the attack, not to invent a new way for the page
to stop working for someone.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.views import maybe_autopilot_held_review
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class ReviewOpenAutopilotTriggerTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Fetch Metadata School",
            slug="fetch-metadata-school",
            subdomain="fetch-metadata-school",
            is_active=True,
            is_approved=True,
        )
        self.admin = User.objects.create_user(
            username="fetch-metadata-admin", password="x", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.bundle = MigrationBundle.objects.create(
            label="fetch-metadata",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="fetch-metadata-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )
        self.held = MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain="academics",
            row_index=1,
            issue_class="missing_required",
            payload={
                "error": "missing subject",
                "artifact": "school_stats_2026-01-18.pdf",
                "source_row": {"page": "2", "line": "stat summary"},
            },
        )

    def _open(self, **headers):
        request = RequestFactory().get("/review/", **headers)
        request.user = self.admin
        return maybe_autopilot_held_review(request, self.bundle, user=self.admin)

    def _still_pending(self) -> bool:
        self.held.refresh_from_db()
        return self.held.status == MigrationQuarantineRecord.Status.PENDING

    def test_an_embedded_image_request_does_not_close_rows(self):
        self.assertIsNone(self._open(HTTP_SEC_FETCH_DEST="image"))
        self.assertTrue(
            self._still_pending(),
            "a cross-site <img> tag closed a tenant's held rows",
        )

    def test_an_iframe_request_does_not_close_rows(self):
        self.assertIsNone(self._open(HTTP_SEC_FETCH_DEST="iframe"))
        self.assertTrue(self._still_pending())

    def test_a_prefetch_does_not_close_rows(self):
        self.assertIsNone(
            self._open(HTTP_SEC_FETCH_DEST="document", HTTP_SEC_PURPOSE="prefetch")
        )
        self.assertTrue(
            self._still_pending(),
            "a link prefetch triaged a bundle nobody opened",
        )

    def test_a_real_navigation_still_runs_autopilot(self):
        response = self._open(
            HTTP_SEC_FETCH_DEST="document",
            HTTP_SEC_FETCH_MODE="navigate",
            HTTP_SEC_FETCH_SITE="same-origin",
        )
        self.assertIsNotNone(response, "the whole point of review-open autopilot")
        self.assertIn("autopilot_done=", response.url)
        self.assertFalse(self._still_pending())

    def test_a_client_without_fetch_metadata_still_runs_autopilot(self):
        # curl, the test client, an old browser. Fail-open here is deliberate:
        # none of them is the attack, and refusing them would break the feature
        # for exactly the callers that cannot be the threat.
        response = self._open()
        self.assertIsNotNone(response)
        self.assertFalse(self._still_pending())
