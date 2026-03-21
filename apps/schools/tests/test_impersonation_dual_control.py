# Four-eyes: high-risk schools require a second platform operator email.

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig, ImpersonationLog


@override_settings(
    JIT_IMPERSONATION_REQUIRE_CONSENT=True,
    IMPERSONATION_REQUIRE_JUSTIFICATION=True,
)
class ImpersonationDualControlTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.first()
        if not self.region:
            self.region = RegionConfig.objects.create(
                code="CM",
                name="Cameroon",
                default_language="en",
                timezone="Africa/Douala",
            )
        self.school = School.objects.create(
            name="Dual Control School",
            slug="dual-control-school",
            subdomain="dual-control-school",
            is_active=True,
            default_region=self.region,
            impersonation_consent_granted_at=timezone.now(),
            impersonation_dual_control=True,
        )
        self.actor = User.objects.create_user(
            username="dual_actor",
            email="actor@example.com",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.peer = User.objects.create_user(
            username="dual_peer",
            email="peer@example.com",
            password="pass12345",
            is_staff=True,
            is_superuser=False,
            role=User.Role.SUPERADMIN,
        )

    def test_dual_control_requires_peer_email(self):
        self.client.force_login(self.actor)
        self.school.impersonation_consent_granted_by_id = self.actor.id
        self.school.save()
        response = self.client.post(
            reverse("super:switch_to_tenant"),
            data={
                "school_id": str(self.school.id),
                "impersonation_reason": "Testing dual control gate.",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("super", response.url or "")
        self.assertNotIn("impersonate=", response.url or "")

    def test_dual_control_succeeds_with_peer(self):
        self.client.force_login(self.actor)
        self.school.impersonation_consent_granted_by_id = self.actor.id
        self.school.save()
        response = self.client.post(
            reverse("super:switch_to_tenant"),
            data={
                "school_id": str(self.school.id),
                "impersonation_reason": "Testing dual control gate with peer.",
                "peer_approver_email": "peer@example.com",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("impersonate=", response.url or "")
        log = ImpersonationLog.objects.filter(
            school=self.school, action=ImpersonationLog.Action.SWITCH
        ).order_by("-created_at").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.peer_actor_id, self.peer.id)
