"""Platform operator identity hub — models, scopes, and /super/team/ routes."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.platform_runtime.models_operator_identity import (
    PlatformOperatorInvite,
    PlatformOperatorProfile,
    PlatformOperatorPromotionRequest,
)
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TEAM_MANAGE,
    PLATFORM_SCOPE_TEAM_READ,
    CANONICAL_PLATFORM_ADMIN_USERNAME,
    ensure_platform_operator_profile,
    is_canonical_platform_admin,
    user_effective_platform_scopes,
    user_has_platform_scope,
    user_is_platform_operator,
    user_may_offboard_operator,
)
from apps.schools.super_views_operator_team import (
    operator_invite_accept,
    super_operator_team_invite,
    super_operator_team_offboard,
    super_operator_team_promote,
    super_operator_team_promotion_decide,
    super_operator_team_reactivate,
    super_operator_team_roster,
    super_operator_team_suspend,
)


def _manager_request(factory, method, path, user, data=None):
    data = data or {}
    if method == "GET":
        request = factory.get(path, HTTP_HOST="manager.runmycampus.com")
    else:
        request = factory.post(path, data, HTTP_HOST="manager.runmycampus.com")
    request.user = user
    request.public_host_kind = "manager"
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def _canonical_admin_user():
    User = get_user_model()
    admin, _ = User.objects.update_or_create(
        username=CANONICAL_PLATFORM_ADMIN_USERNAME,
        defaults={
            "email": "admin@example.com",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )
    admin.set_password("admin")
    admin.save(update_fields=["password"])
    return admin


class OperatorIdentityHelpersTests(TestCase):
    def test_superuser_has_all_scopes(self):
        User = get_user_model()
        user = User.objects.create_superuser("op1", "op1@example.com", "pass12345")
        self.assertTrue(user_is_platform_operator(user))
        self.assertTrue(user_has_platform_scope(user, PLATFORM_SCOPE_TEAM_READ))
        self.assertIn(PLATFORM_SCOPE_TEAM_MANAGE, user_effective_platform_scopes(user))

    def test_profile_tier_grants_scopes(self):
        User = get_user_model()
        user = User.objects.create_user(
            "support1", "support1@example.com", "pass12345", is_staff=True
        )
        PlatformOperatorProfile.objects.create(
            user=user,
            status=PlatformOperatorProfile.Status.ACTIVE,
            tier="support",
        )
        self.assertTrue(user_is_platform_operator(user))
        self.assertTrue(user_has_platform_scope(user, PLATFORM_SCOPE_TEAM_READ))
        self.assertFalse(user_has_platform_scope(user, PLATFORM_SCOPE_TEAM_MANAGE))

    def test_canonical_admin_cannot_be_offboarded(self):
        User = get_user_model()
        admin = _canonical_admin_user()
        actor = User.objects.create_user(
            username="manager1",
            email="manager1@example.com",
            password="pass12345",
            is_staff=True,
            is_superuser=True,
        )
        self.assertTrue(is_canonical_platform_admin(admin))
        self.assertFalse(user_may_offboard_operator(actor, admin))

    def test_ensure_platform_operator_profile_break_glass_for_admin(self):
        admin = _canonical_admin_user()
        ensure_platform_operator_profile(admin)
        profile = PlatformOperatorProfile.objects.get(user=admin)
        self.assertEqual(profile.tier, "break_glass")
        self.assertEqual(profile.status, PlatformOperatorProfile.Status.ACTIVE)


@override_settings(
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
    ROOT_URLCONF="config.manager_urls",
)
class OperatorTeamHubViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="superop",
            email="superop@example.com",
            password="pass12345",
            is_staff=True,
            is_superuser=True,
        )
        self.factory = RequestFactory()

    def test_roster_view_renders_for_superuser(self):
        request = _manager_request(
            self.factory, "GET", "/super/team/", self.admin
        )
        response = super_operator_team_roster(request)
        self.assertEqual(response.status_code, 200)

    def test_invite_post_creates_pending_token(self):
        request = _manager_request(
            self.factory,
            "POST",
            "/super/team/invite/",
            self.admin,
            {"email": "newop@example.com", "tier": "support"},
        )
        response = super_operator_team_invite(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PlatformOperatorInvite.objects.count(), 1)

    def test_invite_accept_creates_operator_profile(self):
        invite = PlatformOperatorInvite.objects.create(
            email="accept@example.com",
            tier="observer",
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=3),
        )
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.post(
            f"/authentication/operator-invite/{invite.token}/",
            {
                "username": "acceptedop",
                "password": "longpass123",
                "password2": "longpass123",
            },
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = AnonymousUser()
        request.session = {}
        request._messages = FallbackStorage(request)
        response = operator_invite_accept(request, token=invite.token)
        self.assertEqual(response.status_code, 302)
        User = get_user_model()
        user = User.objects.get(username="acceptedop")
        self.assertTrue(
            PlatformOperatorProfile.objects.filter(
                user=user, status=PlatformOperatorProfile.Status.ACTIVE
            ).exists()
        )

    def test_promotion_dual_control_flow(self):
        User = get_user_model()
        target = User.objects.create_user(
            "targetop", "target@example.com", "pass12345", is_staff=True
        )
        PlatformOperatorProfile.objects.create(
            user=target,
            status=PlatformOperatorProfile.Status.ACTIVE,
            tier="observer",
        )
        peer = User.objects.create_user(
            username="peerop",
            email="peer@example.com",
            password="pass12345",
            is_staff=True,
            is_superuser=True,
        )
        create_request = _manager_request(
            self.factory,
            "POST",
            "/super/team/promote/",
            self.admin,
            {
                "target_user_id": target.pk,
                "tier": "support",
                "peer_approver_id": peer.pk,
                "reason": "Onboarding complete",
            },
        )
        super_operator_team_promote(create_request)
        promo = PlatformOperatorPromotionRequest.objects.get()
        decide_request = _manager_request(
            self.factory,
            "POST",
            f"/super/team/promote/{promo.pk}/decide/",
            peer,
            {"decision": "approve"},
        )
        super_operator_team_promotion_decide(decide_request, promo_id=promo.pk)
        promo.refresh_from_db()
        profile = PlatformOperatorProfile.objects.get(user=target)
        self.assertEqual(promo.status, PlatformOperatorPromotionRequest.Status.APPROVED)
        self.assertEqual(profile.tier, "support")


    def test_offboard_canonical_admin_is_blocked(self):
        admin = _canonical_admin_user()
        ensure_platform_operator_profile(admin)
        request = _manager_request(
            self.factory,
            "POST",
            f"/super/team/{admin.pk}/offboard/",
            admin,
        )
        response = super_operator_team_offboard(request, user_id=admin.pk)
        self.assertEqual(response.status_code, 302)
        profile = PlatformOperatorProfile.objects.get(user=admin)
        self.assertEqual(profile.status, PlatformOperatorProfile.Status.ACTIVE)

    def test_suspend_and_reactivate_operator(self):
        User = get_user_model()
        target = User.objects.create_user(
            "suspendop",
            "suspendop@example.com",
            "pass12345",
            is_staff=True,
        )
        PlatformOperatorProfile.objects.create(
            user=target,
            status=PlatformOperatorProfile.Status.ACTIVE,
            tier="support",
        )
        suspend_request = _manager_request(
            self.factory,
            "POST",
            f"/super/team/{target.pk}/suspend/",
            self.admin,
        )
        super_operator_team_suspend(suspend_request, user_id=target.pk)
        profile = PlatformOperatorProfile.objects.get(user=target)
        self.assertEqual(profile.status, PlatformOperatorProfile.Status.SUSPENDED)
        reactivate_request = _manager_request(
            self.factory,
            "POST",
            f"/super/team/{target.pk}/reactivate/",
            self.admin,
        )
        super_operator_team_reactivate(reactivate_request, user_id=target.pk)
        profile.refresh_from_db()
        self.assertEqual(profile.status, PlatformOperatorProfile.Status.ACTIVE)


class OperatorTeamUrlSmokeTests(SimpleTestCase):
    def test_named_urls_resolve(self):
        self.assertEqual(reverse("super:operator_team_roster"), "/super/team/")
        self.assertEqual(reverse("super:operator_team_invite"), "/super/team/invite/")
        self.assertIn(
            "/suspend/",
            reverse("super:operator_team_suspend", kwargs={"user_id": 1}),
        )
        self.assertIn(
            "/reactivate/",
            reverse("super:operator_team_reactivate", kwargs={"user_id": 1}),
        )
