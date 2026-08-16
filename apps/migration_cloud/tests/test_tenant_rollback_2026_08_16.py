"""Phase 2 — tenant-side full-bundle rollback (resume+rollback parity).

The tenant already had a self-serve REPAIR (resume) control; it had no way to
REVERT an import it ran. These tests lock the new ``TenantMigrationRollbackView``:
it is admin-gated (destructive), it refuses to delete without an explicit
``confirm=1`` (two-step), and it delegates to the shared, honest
``connector_rollback.rollback_bundle``. Plus the review-page panel (``_build_rollback``)
only appears once a live import has actually landed rows.

RequestFactory (not the Client) drives the view — the host-split urlconf makes a
Client test mass-false-RED (the same reason the apply-gate suite documents).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.accounts.decorators import user_is_tenant_admin
from apps.accounts.models import User
from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.views_tenant_upload import (
    _TenantAdminWriteRequiredMixin,
    TenantMigrationRollbackView,
    _build_rollback,
)
from apps.schools.models import School, SchoolMembership

_ROLLBACK_BUNDLE = "apps.migration_cloud.services.connector_rollback.rollback_bundle"


class BuildRollbackPanelTests(SimpleTestCase):
    """The review-page rollback panel only appears once a live import landed rows."""

    def _bundle(self, apply_totals):
        return SimpleNamespace(pk=1, mapping_summary={"apply_totals": apply_totals})

    def test_hidden_before_any_import(self):
        self.assertIsNone(_build_rollback(SimpleNamespace(pk=1, mapping_summary={})))

    def test_hidden_on_dry_run_preview(self):
        self.assertIsNone(self._bundle_result({"dry_run": True, "created": 9}))

    def test_hidden_when_nothing_landed(self):
        self.assertIsNone(self._bundle_result({"created": 0, "updated": 0}))

    def test_shown_after_live_apply_with_rows(self):
        panel = self._bundle_result({"created": 5, "updated": 2})
        self.assertIsNotNone(panel)
        self.assertEqual(panel["created"], 5)
        self.assertEqual(panel["updated"], 2)
        self.assertTrue(panel["has_updates"])

    def _bundle_result(self, apply_totals):
        return _build_rollback(self._bundle(apply_totals))


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class TenantRollbackViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Rollback Gate School", slug="rollback-gate", subdomain="rollback-gate",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school, idempotency_key="mc-test-rollback-gate-0001",
        )
        self.member = User.objects.create_user(
            username="rb-teacher", password="x", role=User.Role.TEACHER, is_staff=False
        )
        SchoolMembership.objects.create(
            user=self.member, school=self.school, role=User.Role.TEACHER,
            is_school_owner=False, is_primary=True,
        )
        self.admin = User.objects.create_user(
            username="rb-admin", password="x", role=User.Role.ADMIN, is_staff=False
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN,
            is_school_owner=True, is_primary=True,
        )

    def _post(self, user, data=None):
        request = self.factory.post(
            "/school/setup/migration-cloud/bundle/rollback/", data or {}
        )
        request.user = user
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_non_admin_member_rollback_is_denied(self):
        self.assertFalse(user_is_tenant_admin(self.member, self.school))
        with mock.patch(_ROLLBACK_BUNDLE) as rb:
            request = self._post(self.member, {"confirm": "1"})
            with self.assertRaises(PermissionDenied):
                TenantMigrationRollbackView.as_view()(request, bundle_id=self.bundle.pk)
            rb.assert_not_called()  # nothing was deleted

    def test_admin_without_confirm_does_not_delete(self):
        self.assertTrue(user_is_tenant_admin(self.admin, self.school))
        with mock.patch(_ROLLBACK_BUNDLE) as rb:
            request = self._post(self.admin, {})  # NO confirm
            resp = TenantMigrationRollbackView.as_view()(request, bundle_id=self.bundle.pk)
        rb.assert_not_called()  # two-step guard: no confirm -> no revert
        self.assertEqual(resp.status_code, 302)

    def test_admin_confirm_delegates_to_rollback_bundle(self):
        result = {"ok": True, "applied": True, "reverted_total": 3, "runs": [],
                  "not_reverted": [], "message": "Reverted 3 record(s) across 1 run(s)."}
        with mock.patch(_ROLLBACK_BUNDLE, return_value=result) as rb:
            request = self._post(self.admin, {"confirm": "1"})
            resp = TenantMigrationRollbackView.as_view()(request, bundle_id=self.bundle.pk)
        rb.assert_called_once()
        self.assertEqual(rb.call_args.kwargs.get("confirm"), True)
        self.assertEqual(rb.call_args.kwargs.get("actor"), self.admin)
        self.assertEqual(resp.status_code, 302)

    def test_unauthenticated_is_bounced_to_login(self):
        request = self._post(AnonymousUser(), {"confirm": "1"})
        resp = TenantMigrationRollbackView.as_view()(request, bundle_id=self.bundle.pk)
        self.assertEqual(resp.status_code, 302)

    def test_rollback_view_carries_the_admin_write_gate(self):
        self.assertIn(_TenantAdminWriteRequiredMixin, TenantMigrationRollbackView.__mro__)
