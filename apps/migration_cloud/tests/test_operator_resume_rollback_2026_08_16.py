"""Phase 3 — operator-side resume + FULL-bundle rollback (parity with the tenant flow).

The operator console could only roll back one run at a time (MigrationCloudRollbackView
is per-run) and had no resume button. These lock the two new operator POST views:
MigrationCloudBundleRepairView (resume, delegates to repair.repair_bundle off the HTTP
thread) and MigrationCloudBundleRollbackView (full-bundle revert, delegates to the
shared connector_rollback.rollback_bundle, requires confirm=1). Both redirect back to
the bundle detail with a message.

RequestFactory drives the views directly (host-split urlconf), and the redirect target
is mocked so the assertions isolate the confirm-gate + delegation, not URL reversing.
"""
from __future__ import annotations

from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import User
from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.views import (
    MigrationCloudBundleRepairView,
    MigrationCloudBundleRollbackView,
)
from apps.schools.models import School

_ROLLBACK_BUNDLE = "apps.migration_cloud.services.connector_rollback.rollback_bundle"
_REPAIR_BUNDLE = "apps.migration_cloud.repair.repair_bundle"
_DETAIL_URL = "apps.migration_cloud.views._bundle_detail_url"


@override_settings(ALLOWED_HOSTS=["*"])
class OperatorResumeRollbackTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Op Resume/Rollback", slug="op-rrb", subdomain="op-rrb", is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school, idempotency_key="mc-op-rrb-0001",
        )
        self.staff = User.objects.create_user(
            username="op-staff", password="x", is_staff=True
        )

    def _post(self, data=None, user=None):
        request = self.factory.post("/super/migration/x/", data or {})
        request.user = user or self.staff
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    # ── resume ────────────────────────────────────────────────────────────
    def test_repair_delegates_off_http_and_redirects(self):
        from apps.migration_cloud.repair import RepairResult

        rr = RepairResult(ok=True, ran=False, queued=True, message="Repair is queued.", outbox_id="x")
        with mock.patch(_REPAIR_BUNDLE, return_value=rr) as repair, \
                mock.patch(_DETAIL_URL, return_value="/super/migration/1/"):
            resp = MigrationCloudBundleRepairView.as_view()(
                self._post(), bundle_id=self.bundle.pk
            )
        repair.assert_called_once()
        self.assertEqual(repair.call_args.kwargs.get("off_http"), True)
        self.assertEqual(resp.status_code, 302)

    def test_repair_requires_login(self):
        resp = MigrationCloudBundleRepairView.as_view()(
            self._post(user=AnonymousUser()), bundle_id=self.bundle.pk
        )
        self.assertEqual(resp.status_code, 302)  # LoginRequiredMixin bounce

    # ── full-bundle rollback ───────────────────────────────────────────────
    def test_rollback_without_confirm_does_not_delete(self):
        with mock.patch(_ROLLBACK_BUNDLE) as rb, mock.patch(_DETAIL_URL, return_value="/x/"):
            resp = MigrationCloudBundleRollbackView.as_view()(
                self._post({}), bundle_id=self.bundle.pk  # NO confirm
            )
        rb.assert_not_called()
        self.assertEqual(resp.status_code, 302)

    def test_rollback_confirm_delegates_with_confirm_true(self):
        result = {"ok": True, "applied": True, "reverted_total": 2, "runs": [],
                  "not_reverted": [], "message": "Reverted 2 record(s) across 1 run(s)."}
        with mock.patch(_ROLLBACK_BUNDLE, return_value=result) as rb, \
                mock.patch(_DETAIL_URL, return_value="/x/"):
            resp = MigrationCloudBundleRollbackView.as_view()(
                self._post({"confirm": "1"}), bundle_id=self.bundle.pk
            )
        rb.assert_called_once()
        self.assertEqual(rb.call_args.kwargs.get("confirm"), True)
        self.assertEqual(rb.call_args.kwargs.get("actor"), self.staff)
        self.assertEqual(resp.status_code, 302)

    def test_rollback_partial_result_still_redirects(self):
        # Applied but not a clean slate -> warning path, still a normal redirect.
        result = {"ok": False, "applied": True, "reverted_total": 1, "runs": [],
                  "not_reverted": [{"migration_type": "structure", "reason": "shared scaffold"}],
                  "message": "Reverted 1; 1 domain left in place."}
        with mock.patch(_ROLLBACK_BUNDLE, return_value=result), \
                mock.patch(_DETAIL_URL, return_value="/x/"):
            resp = MigrationCloudBundleRollbackView.as_view()(
                self._post({"confirm": "1"}), bundle_id=self.bundle.pk
            )
        self.assertEqual(resp.status_code, 302)
