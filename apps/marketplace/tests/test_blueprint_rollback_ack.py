"""N20 parity: blueprint marketplace rollback requires ROLLBACK acknowledgment."""

import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.policies.models import PolicyBundle, TenantBlueprint
from apps.platform_runtime.models import PlatformEventLog
from apps.schools.models import School
from apps.schools.tests.manager_client import login_manager_control_plane


@override_settings(
    ALLOWED_HOSTS=["*"],
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class BlueprintRollbackAckTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="BP Rollback School",
            slug="bp-rollback",
            subdomain="bp-rollback",
            is_active=True,
        )
        self.bundle = PolicyBundle.objects.create(
            school=self.school,
            name="Active bundle",
            policy_snapshot={"k": 1},
        )
        self.tb = TenantBlueprint.objects.create(
            school=self.school,
            active_bundle=self.bundle,
        )
        self.superuser = User.objects.create_superuser("su_bp_rb", "su_bp_rb@x.edu", "pw")
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def _post_rollback(self, **extra):
        c = Client()
        login_manager_control_plane(c, self.superuser, password="pw")
        data = {
            "action": "rollback",
            "school_id": str(self.school.pk),
            "bundle_id": "",
        }
        data.update(extra)
        return c.post(
            reverse("super:blueprint_marketplace"),
            data,
            HTTP_HOST="manager.runmycampus.com",
        )

    def test_rollback_without_keyword_rejected(self):
        r = self._post_rollback(confirm_blueprint_rollback="no")
        self.assertEqual(r.status_code, 302)
        self.tb.refresh_from_db()
        self.assertEqual(self.tb.active_bundle_id, self.bundle.pk)

    def test_rollback_with_rollback_clears_bundle(self):
        r = self._post_rollback(confirm_blueprint_rollback="ROLLBACK")
        self.assertEqual(r.status_code, 302)
        self.tb.refresh_from_db()
        self.assertIsNone(self.tb.active_bundle_id)
        log = PlatformEventLog.objects.filter(event_type="blueprint_rolled_back").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.payload.get("previous_bundle_id"), self.bundle.pk)
        self.assertIsNone(log.payload.get("new_bundle_id"))
        self.assertEqual(log.payload.get("school_id"), str(self.school.pk))
