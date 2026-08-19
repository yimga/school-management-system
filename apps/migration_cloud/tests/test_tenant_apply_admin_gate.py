"""S2 fix — the Migration Cloud tenant APPLY/upload/repair surfaces are admin-gated.

The hole (S2 = 45): every write view in ``views_tenant_upload.py`` was
``(LoginRequiredMixin, View)`` with NO role check, and ``_request_school`` falls
back to the caller's FIRST school membership with no role filter. Because
SAML/SCIM provisions a membership for EVERY IdP user, the effective gate was
"authenticated + ANY membership" — so a teacher / parent / student could POST
``confirm=1`` and have ``apply_bundle`` irreversibly overwrite the school's live
data across the landable domains (only students + grades have rollback handlers).

These tests are FAILS-FIRST: against HEAD (before the gate) a non-admin member's
``confirm=1`` POST reaches ``apply_bundle`` and no ``PermissionDenied`` is raised,
so ``test_non_admin_member_apply_confirm_is_denied`` FAILS. After the fix the same
POST is refused (403 / ``PermissionDenied``) BEFORE ``apply_bundle`` runs, while a
school admin / owner still proceeds to the live write.

RequestFactory (not the Client) drives the views directly — the host-split urlconf
makes a Client test mass-false-RED (``KeyError:'admin'`` / host-guard 302 noise).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.decorators import user_is_tenant_admin
from apps.accounts.models import User
from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.views_tenant_upload import (
    _TenantAdminWriteRequiredMixin,
    TenantMigrationApplyView,
    TenantMigrationProgressView,
    TenantMigrationRepairView,
    TenantMigrationReviewView,
    TenantMigrationUploadView,
)
from apps.schools.models import School, SchoolMembership

_ENQUEUE_APPLY = "apps.migration_cloud.celery_tasks.enqueue_apply"


def _fake_apply_result():
    """A well-formed stand-in for ``apply_bundle``'s return so the admin path can
    render past the summary without touching the real orchestrator/DB writes."""
    return SimpleNamespace(
        dry_run=False,
        status="APPLIED",
        total_created=0,
        total_updated=0,
        total_quarantined=0,
        per_artifact=[],
    )


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class TenantMigrationApplyAdminGateTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Apply Gate School",
            slug="apply-gate-school",
            subdomain="apply-gate-school",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            idempotency_key="mc-test-apply-gate-0001",
        )

        # A teacher provisioned WITH a school membership — exactly what SAML/SCIM
        # mints for every IdP user. Not the tenant-admin tier.
        self.member = User.objects.create_user(
            username="teacher-member", password="x", role=User.Role.TEACHER, is_staff=False
        )
        SchoolMembership.objects.create(
            user=self.member,
            school=self.school,
            role=User.Role.TEACHER,
            is_school_owner=False,
            is_primary=True,
        )

        # A school admin (ADMIN_LIKE role) — must still pass.
        self.admin = User.objects.create_user(
            username="school-admin", password="x", role=User.Role.ADMIN, is_staff=False
        )

        # A pure owner: membership owner flag, NON-admin role — must also pass
        # (proves the fix does not over-restrict self-service owners).
        self.owner = User.objects.create_user(
            username="school-owner", password="x", role=User.Role.TEACHER, is_staff=False
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.TEACHER,
            is_school_owner=True,
            is_primary=True,
        )

    def _post(self, user, data=None):
        request = self.factory.post("/school/setup/migration-cloud/bundle/apply/", data or {})
        request.user = user
        request.school = self.school
        # Give the render/messages path somewhere to write (best-effort; the
        # security assertions below do not depend on the final render succeeding).
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    # ── the core fails-first proof ─────────────────────────────────────────

    def test_non_admin_member_apply_confirm_is_denied(self):
        """A non-admin member POSTing confirm=1 is refused BEFORE apply runs.

        FAILS against HEAD (no gate → apply_bundle is called, no PermissionDenied);
        PASSES after the fix."""
        self.assertFalse(user_is_tenant_admin(self.member, self.school))
        with mock.patch(_ENQUEUE_APPLY) as enqueue_mock:
            request = self._post(self.member, {"confirm": "1"})
            with self.assertRaises(PermissionDenied):
                TenantMigrationApplyView.as_view()(request, bundle_id=self.bundle.pk)
            enqueue_mock.assert_not_called()  # no durable write was queued

    def test_admin_apply_confirm_reaches_live_write(self):
        """A school admin's confirm=1 passes the gate and reaches the live apply."""
        self.assertTrue(user_is_tenant_admin(self.admin, self.school))
        queued = SimpleNamespace(outbox_id="tenant-admin-apply")
        with mock.patch(_ENQUEUE_APPLY, return_value=queued) as enqueue_mock:
            request = self._post(self.admin, {"confirm": "1"})
            TenantMigrationApplyView.as_view()(request, bundle_id=self.bundle.pk)
        enqueue_mock.assert_called_once()
        # confirm=1 ⇒ the live (non-dry-run) write path.
        self.assertEqual(enqueue_mock.call_args.kwargs.get("dry_run"), False)

    def test_owner_without_admin_role_reaches_live_write(self):
        """A self-service owner (membership flag, non-admin role) still proceeds —
        the fix adds privilege, it does not lock owners out."""
        self.assertTrue(user_is_tenant_admin(self.owner, self.school))
        queued = SimpleNamespace(outbox_id="tenant-owner-apply")
        with mock.patch(_ENQUEUE_APPLY, return_value=queued) as enqueue_mock:
            request = self._post(self.owner, {"confirm": "1"})
            TenantMigrationApplyView.as_view()(request, bundle_id=self.bundle.pk)
        enqueue_mock.assert_called_once_with(self.bundle.pk, dry_run=False)

    def test_unauthenticated_is_bounced_to_login(self):
        """Anonymous callers hit LoginRequiredMixin (302 → login), not a 403."""
        request = self._post(AnonymousUser(), {"confirm": "1"})
        resp = TenantMigrationApplyView.as_view()(request, bundle_id=self.bundle.pk)
        self.assertEqual(resp.status_code, 302)

    # ── the sibling write surfaces are gated too ───────────────────────────

    def test_upload_write_surface_denied_for_non_admin(self):
        request = self.factory.post("/school/setup/migration-cloud/upload/", {})
        request.user = self.member
        request.school = self.school
        with self.assertRaises(PermissionDenied):
            TenantMigrationUploadView.as_view()(request)

    def test_repair_get_renders_the_review_surface(self):
        """Refreshing /repair/ must not 405 — it is the same review canvas."""
        request = self.factory.get("/school/setup/migration-cloud/bundle/repair/")
        request.user = self.admin
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        resp = TenantMigrationRepairView.as_view()(request, bundle_id=self.bundle.pk)
        self.assertEqual(resp.status_code, 200)
        request = self._post(self.member, {})
        with self.assertRaises(PermissionDenied):
            TenantMigrationRepairView.as_view()(request, bundle_id=self.bundle.pk)

    def test_review_write_surface_denied_for_non_admin(self):
        request = self._post(self.member, {})
        with self.assertRaises(PermissionDenied):
            TenantMigrationReviewView.as_view()(request, bundle_id=self.bundle.pk)

    # ── scope documentation: read poller stays lighter, writes are gated ───

    def test_gating_topology_write_views_gated_progress_lighter(self):
        """The four WRITE views carry the admin gate; the read-only progress
        poller deliberately stays on LoginRequiredMixin only (per the mandate)."""
        for view in (
            TenantMigrationUploadView,
            TenantMigrationReviewView,
            TenantMigrationApplyView,
            TenantMigrationRepairView,
        ):
            self.assertIn(_TenantAdminWriteRequiredMixin, view.__mro__, view.__name__)
        self.assertNotIn(
            _TenantAdminWriteRequiredMixin, TenantMigrationProgressView.__mro__
        )
