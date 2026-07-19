"""G6 — a roster-minted org must not be a live, unprovisioned husk.

Found by the provisioning audit (2026-07-19). ``School.is_active`` defaults True,
so ``get_or_create``-ing an org with no ``is_active`` left a live School with no
tenant schema / seed / owner: it reads "ready" to every healer (the husk class
the audit centers on) and 500s on use. New orgs must land ``is_active=False`` and
be handed to the real provisioning pipeline; an existing LIVE org must never be
flipped inactive by a re-sync (get_or_create ignores ``defaults`` on an existing
row).

The provisioning enqueue is fired via ``transaction.on_commit`` (immediate in the
autocommit request path; after-commit if a caller ever wraps it), so these tests
run it explicitly with ``captureOnCommitCallbacks`` and patch the dispatch to keep
mail/schema side effects out of the test.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School

_DISPATCH = "apps.schools.tasks.dispatch_provision_school"


@override_settings(RMC_ONEROSTER_ACCESS_TOKEN="prov-token")
class OneRosterNewOrgIsProvisionedNotHuskTests(TestCase):
    def setUp(self):
        cache.clear()
        self.headers = {"HTTP_AUTHORIZATION": "Bearer prov-token"}

    def _put_org(self, sourced_id: str, identifier: str, name: str = "Some School"):
        url = reverse(
            "api:api-roster-v1p2-org-detail", kwargs={"sourced_id": sourced_id}
        )
        return self.client.put(
            url,
            data={"org": {"name": name, "identifier": identifier}},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex,
            **self.headers,
        )

    def test_new_org_lands_inactive_and_enqueued_for_provisioning(self):
        with mock.patch(_DISPATCH) as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self._put_org("org-new", "new-district-school")
        self.assertEqual(resp.status_code, 201)
        school = School.objects.get(slug="new-district-school")
        self.assertFalse(
            school.is_active,
            "a roster-minted org must NOT be a live husk -- it lands inactive "
            "until the real pipeline provisions it into usability",
        )
        dispatch.assert_called_once_with(str(school.pk))

    def test_existing_live_org_is_not_deactivated_by_resync(self):
        live = School.objects.create(
            name="Live District",
            slug="live-district",
            subdomain="live-district",
            is_active=True,
        )
        with mock.patch(_DISPATCH) as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self._put_org(
                    "org-live", "live-district", name="Live District Renamed"
                )
        self.assertEqual(resp.status_code, 200)
        live.refresh_from_db()
        self.assertTrue(
            live.is_active,
            "re-syncing an existing LIVE tenant must never flip it inactive -- "
            "get_or_create ignores defaults on an existing row",
        )
        dispatch.assert_not_called()

    def test_csv_importer_new_org_is_inactive_and_enqueued(self):
        from apps.api.oneroster_csv_importer import _apply_orgs

        report: dict = {"orgs": {}}
        with mock.patch(_DISPATCH) as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                _apply_orgs(
                    [
                        {
                            "sourcedId": "csv-org-1",
                            "name": "CSV School",
                            "identifier": "csv-school-1",
                        }
                    ],
                    report,
                )
        school = School.objects.get(slug="csv-school-1")
        self.assertFalse(
            school.is_active,
            "the CSV importer must also land a new org inactive, not as a husk",
        )
        dispatch.assert_called_once_with(str(school.pk))
