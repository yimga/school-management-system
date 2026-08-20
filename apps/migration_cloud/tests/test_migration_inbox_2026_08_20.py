"""The migration inbox: one tray that answers "is any import in trouble?".

Before this surface existed, an import's state lived only on its own review
page, so an apply whose worker had died was invisible from every landing
surface — which is how a wedged import ran for a day without anyone being told.

The tray composes each row from the SAME helpers the review page uses, so the
badge here cannot drift from the badge there. These tests pin the three things
that make it worth having: a wedged import is flagged and sorted to the top, a
healthy one is not, and the tray never leaks another school's imports.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.migration_cloud.models import (
    BundleStatus,
    MigrationBundle,
    MigrationProgressEvent,
)
from apps.migration_cloud.views_tenant_upload import TenantMigrationInboxView
from apps.schools.models import School, SchoolMembership


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class MigrationInboxTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Inbox {uid}", slug=f"inbox-{uid}", subdomain=f"inbox{uid}", is_active=True
        )
        self.other_school = School.objects.create(
            name=f"Other {uid}", slug=f"other-{uid}", subdomain=f"other{uid}", is_active=True
        )
        self.admin = User.objects.create_user(
            username=f"inbox-admin-{uid}", password="x", role=User.Role.ADMIN, is_staff=False
        )
        self.member = User.objects.create_user(
            username=f"inbox-member-{uid}", password="x", role=User.Role.TEACHER, is_staff=False
        )
        SchoolMembership.objects.create(
            user=self.member,
            school=self.school,
            role=User.Role.TEACHER,
            is_school_owner=False,
            is_primary=True,
        )

    def _bundle(self, *, status, school=None):
        # idempotency_key is unique and defaults blank, so every bundle in one
        # test needs its own or the second create() trips the constraint.
        return MigrationBundle.objects.create(
            school=school or self.school,
            status=status,
            idempotency_key=f"mc-inbox-{uuid.uuid4().hex[:16]}",
        )

    def _cold_event(self, bundle, *, minutes):
        ev = MigrationProgressEvent.objects.create(
            bundle=bundle, kind="artifact_progress", stage="APPLYING"
        )
        MigrationProgressEvent.objects.filter(pk=ev.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes)
        )
        return ev

    def _get(self, user):
        request = self.factory.get("/school/setup/migration-cloud/inbox/")
        request.user = user
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_wedged_import_is_flagged_and_sorted_first(self):
        healthy = self._bundle(status=BundleStatus.MAPPED)
        wedged = self._bundle(status=BundleStatus.APPLYING)
        self._cold_event(wedged, minutes=120)

        response = TenantMigrationInboxView.as_view()(self._get(self.admin))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(f'data-mc-inbox-row="{wedged.pk}"', body)
        self.assertIn(f'data-mc-inbox-row="{healthy.pk}"', body)
        # The one in trouble is announced and comes first in the tray.
        self.assertIn("needs your attention", body)
        self.assertLess(
            body.index(f'data-mc-inbox-row="{wedged.pk}"'),
            body.index(f'data-mc-inbox-row="{healthy.pk}"'),
            "an import that stopped responding must sort above a healthy one",
        )

    def test_healthy_tray_reports_nothing_wrong(self):
        self._bundle(status=BundleStatus.MAPPED)
        response = TenantMigrationInboxView.as_view()(self._get(self.admin))
        body = response.content.decode()
        self.assertNotIn("needs your attention", body)

    def test_another_schools_imports_are_never_listed(self):
        mine = self._bundle(status=BundleStatus.MAPPED)
        theirs = self._bundle(status=BundleStatus.MAPPED, school=self.other_school)
        response = TenantMigrationInboxView.as_view()(self._get(self.admin))
        body = response.content.decode()
        self.assertIn(f'data-mc-inbox-row="{mine.pk}"', body)
        self.assertNotIn(f'data-mc-inbox-row="{theirs.pk}"', body)

    def test_non_admin_member_is_refused(self):
        """The tray enumerates the school's migration history — admin tier only."""
        self._bundle(status=BundleStatus.MAPPED)
        with self.assertRaises(PermissionDenied):
            TenantMigrationInboxView.as_view()(self._get(self.member))
