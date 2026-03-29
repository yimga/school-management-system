"""
Product routing: which URL names serve global platform support vs school contact vs staff triage.

These tests are the executable spec for operators and UX — keep them aligned with portal URLs.
"""

import uuid

from django.test import SimpleTestCase
from django.urls import reverse


class SupportContactRoutingSpecTests(SimpleTestCase):
    def test_global_support_entrypoints_resolve(self):
        self.assertEqual(reverse("portal:support_help_hub"), "/portal/support/hub/")
        tid = uuid.uuid4()
        expected_detail = f"/portal/support/ticket/{tid}/"
        self.assertEqual(
            reverse("portal:support_ticket_detail", kwargs={"ticket_id": tid}),
            expected_detail,
        )
        # Tenant urlconf mirrors root urlconf for portal/* (smoke tests use tenant explicitly).
        self.assertEqual(
            reverse(
                "portal:support_ticket_detail",
                kwargs={"ticket_id": tid},
                urlconf="config.tenant_urls",
            ),
            expected_detail,
        )
        self.assertEqual(reverse("portal:support_request"), "/portal/support/")

    def test_school_contact_parent_and_staff_urls_resolve(self):
        self.assertEqual(
            reverse("portal:parent_contact_school"), "/portal/parent/contact-school/"
        )
        self.assertEqual(
            reverse("portal:staff_contact_request_list"),
            "/portal/staff/contact-requests/",
        )

    def test_direct_messaging_is_separate_from_contact_school(self):
        # Parents are steered to Contact School, not arbitrary DM (see accounts direct_* views).
        self.assertNotEqual(
            reverse("portal:parent_contact_school"),
            reverse("accounts:direct_compose"),
        )
