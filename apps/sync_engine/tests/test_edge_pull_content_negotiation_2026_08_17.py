"""The pull endpoint must accept the Accept header the box actually sends.

Found in production, not in the suite: a live box's every pull came back
``HTTP 406`` while its pushes succeeded. ``pull_bundle`` asks for exactly what the
endpoint produces -- ``Accept: application/x-rmc-sync-bundle+ndjson`` -- but
``SyncBundleDownloadView`` is a DRF ``APIView``, and DRF negotiates a renderer in
``initial()``, BEFORE ``get()`` runs. With only the default JSON renderers registered,
negotiation raised ``NotAcceptable`` and the view was never entered, so no amount of
view-body correctness could have helped.

The existing pull tests missed it because ``APIRequestFactory.get()`` sends no Accept
header at all, so negotiation trivially succeeded on ``*/*`` -- they exercised every
line of the view while never exercising the one header the box really sends. These
tests pin the negotiation itself:

  * the box's exact Accept header returns 200 and the bundle content type;
  * ``Accept: */*`` still works (cron/curl probes, and the JSON error branches);
  * a genuinely unservable Accept still 406s, so the fix widened negotiation by
    exactly one media type rather than disabling it.
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleDownloadView
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.edge_outbox import BUNDLE_CONTENT_TYPE

_SIGN_KEY = "edge-pull-negotiation-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class EdgePullContentNegotiationTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Neg {uid}", slug=f"neg-{uid}", subdomain=f"neg{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"neg_admin_{uid}", password="Test1234", email=f"n{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Njoya", date_of_birth="2012-01-01"
        )
        self.rf = APIRequestFactory()

    def _download(self, **extra):
        request = self.rf.get("/api/v1/sync/bundle/download/", **extra)
        request.school = self.school
        force_authenticate(request, user=self.user)
        return SyncBundleDownloadView.as_view()(request)

    def test_box_accept_header_is_negotiable(self):
        """The exact header apps.sync_engine.edge_outbox.pull_bundle sends."""
        resp = self._download(HTTP_ACCEPT=BUNDLE_CONTENT_TYPE)
        self.assertEqual(
            resp.status_code,
            200,
            f"the box's own Accept header was rejected ({resp.status_code}) -- "
            "content negotiation runs before get(), so this is a 406 the view never sees",
        )
        self.assertIn("x-rmc-sync-bundle", resp["Content-Type"])

    def test_wildcard_accept_still_serves_the_bundle(self):
        """Registering the bundle renderer must not break */* callers."""
        resp = self._download(HTTP_ACCEPT="*/*")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("x-rmc-sync-bundle", resp["Content-Type"])

    def test_no_accept_header_still_serves_the_bundle(self):
        resp = self._download()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("x-rmc-sync-bundle", resp["Content-Type"])

    def test_unservable_accept_is_still_rejected(self):
        """Negotiation was widened by one media type, not switched off."""
        resp = self._download(HTTP_ACCEPT="image/png")
        self.assertEqual(resp.status_code, 406)
