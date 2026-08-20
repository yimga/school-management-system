"""The Install button on the public listing pointed at a path with no route.

The public app-detail page is mounted on ``config.urls`` and ``config.public_urls``
— the base domain — and never on a tenant host. Its Install control posted to a
hardcoded ``/marketplace/settings/install-impact-preview/``, which was wrong four
separate ways:

  * that path exists only on ``config.tenant_urls``, so it 404s on the host
    actually serving the page;
  * the view behind it is ``@require_GET`` and the form was ``method="post"``;
  * it returns ``JsonResponse``, so even a working submit would have shown the
    reader raw JSON instead of an install flow;
  * it needs ``request.school``, which the base domain does not have.

None of that is a typo — it is a genuine cross-host mismatch: the page lives on
one host and the action lives on another. So the fix is not to swap in a
``{% url %}`` (which cannot cross hosts either) but to send the reader to the
app catalog on THEIR school's host, where installing is a real action.

When no school resolves, the button degrades to text. A control that cannot work
is the dead end this whole surface class is about.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.marketplace.views_developer_platform import _install_destination
from apps.schools.models import School, SchoolMembership


class TheTemplateNoLongerCarriesADeadTargetTests(SimpleTestCase):
    def setUp(self):
        self.src = Path("templates/marketplace/public_app_detail.html").read_text(
            encoding="utf-8"
        )

    def test_the_dead_post_target_is_gone(self):
        self.assertNotIn(
            "/marketplace/settings/install-impact-preview/",
            self.src,
            "the listing still posts to a path that resolves on no host",
        )

    def test_the_install_control_is_driven_by_the_resolved_url(self):
        self.assertIn("install_url", self.src)

    def test_there_is_a_text_branch_for_readers_with_no_school(self):
        """No school, no button — the R1 rule applied to a purchase flow."""
        self.assertIn("Open your school workspace to install this app.", self.src)


class WhereInstallActuallyGoesTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Listing {uid}",
            slug=f"listing-{uid}",
            subdomain=f"listing{uid}",
            is_active=True,
        )
        self.member = User.objects.create_user(
            username=f"listing_member_{uid}", password="Test1234", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=self.member,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.stranger = User.objects.create_user(
            username=f"listing_stranger_{uid}", password="Test1234", role=User.Role.ADMIN
        )

    def _request(self, user):
        request = self.factory.get("/marketplace/apps/some-app/")
        request.user = user
        return request

    def test_an_anonymous_reader_gets_no_install_target(self):
        from django.contrib.auth.models import AnonymousUser

        school, url = _install_destination(self._request(AnonymousUser()))
        self.assertIsNone(school)
        self.assertEqual(url, "")

    def test_a_member_is_sent_to_their_own_school(self):
        school, url = _install_destination(self._request(self.member))
        self.assertEqual(school, self.school)
        self.assertTrue(url, "a member with a school got no install destination")
        self.assertIn(
            self.school.subdomain,
            url,
            "the install link does not point at the reader's own host",
        )

    def test_the_destination_is_the_catalog_not_the_json_endpoint(self):
        _school, url = _install_destination(self._request(self.member))
        self.assertIn("/settings/app-catalog/", url)
        self.assertNotIn(
            "install-impact-preview",
            url,
            "the reader is being sent to a JSON endpoint again",
        )

    def test_a_reader_with_no_membership_gets_text_not_a_button(self):
        school, url = _install_destination(self._request(self.stranger))
        self.assertIsNone(school)
        self.assertEqual(url, "")
