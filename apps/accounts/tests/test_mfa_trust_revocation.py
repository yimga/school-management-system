"""Security-state changes revoke durable MFA trusted-browser waivers."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.mfa_device_trust import (
    DEVICE_TRUST_COOKIE,
    device_trust_valid,
    issue_device_trust_token,
    revoke_device_trust,
)
from apps.platform_runtime.operator_identity import (
    ensure_platform_operator_profile,
)
from apps.schools.bulk_operator_team_actions import (
    bulk_apply_operator_team_actions,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class DeviceTrustRevocationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username=f"trust-revoke-{uuid.uuid4().hex[:8]}",
            email="trust-revoke@example.com",
            password="Trust-Revoke-2026!",
            role=User.Role.ADMIN,
        )
        self.school = School.objects.create(
            name="Trust Revocation School",
            slug=f"trust-revoke-{uuid.uuid4().hex[:8]}",
            subdomain=f"trust-revoke-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        self.membership = SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
        )

    def _request(self, token):
        request = self.factory.get("/")
        request.COOKIES[DEVICE_TRUST_COOKIE] = token
        return request

    def _assert_invalid_after_refresh(self, token):
        self.user.refresh_from_db()
        self.assertFalse(device_trust_valid(self._request(token), self.user))

    def test_explicit_security_revocation_is_durable(self):
        token = issue_device_trust_token(self.user)
        self.assertTrue(device_trust_valid(self._request(token), self.user))
        revoke_device_trust(self.user)
        self._assert_invalid_after_refresh(token)

    def test_disable_then_reactivate_does_not_resurrect_old_trust(self):
        token = issue_device_trust_token(self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self._assert_invalid_after_refresh(token)

        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self._assert_invalid_after_refresh(token)

    def test_owner_suspension_then_reactivation_does_not_resurrect_trust(self):
        token = issue_device_trust_token(self.user)
        self.membership.suspended_at = timezone.now()
        self.membership.save(update_fields=["suspended_at", "updated_at"])
        self._assert_invalid_after_refresh(token)

        self.membership.suspended_at = None
        self.membership.save(update_fields=["suspended_at", "updated_at"])
        self._assert_invalid_after_refresh(token)

    def test_owner_or_role_authority_change_revokes_trust(self):
        token = issue_device_trust_token(self.user)
        self.membership.is_school_owner = False
        self.membership.save(update_fields=["is_school_owner", "updated_at"])
        self._assert_invalid_after_refresh(token)

    def test_membership_offboarding_revokes_trust(self):
        token = issue_device_trust_token(self.user)
        self.membership.delete()
        self._assert_invalid_after_refresh(token)

    def test_operator_suspend_and_reactivate_does_not_resurrect_trust(self):
        actor = User.objects.create_user(
            username=f"trust-actor-{uuid.uuid4().hex[:8]}",
            password="Trust-Actor-2026!",
            is_staff=True,
            is_superuser=True,
        )
        target = User.objects.create_user(
            username=f"trust-operator-{uuid.uuid4().hex[:8]}",
            password="Trust-Operator-2026!",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        ensure_platform_operator_profile(actor, tier="break_glass")
        ensure_platform_operator_profile(target, tier="support")
        token = issue_device_trust_token(target)

        outcome = bulk_apply_operator_team_actions(
            user_ids=[target.pk],
            action="suspend",
            actor=actor,
        )
        self.assertTrue(outcome["ok"])
        target.refresh_from_db()
        self.assertFalse(device_trust_valid(self._request(token), target))

        outcome = bulk_apply_operator_team_actions(
            user_ids=[target.pk],
            action="reactivate",
            actor=actor,
        )
        self.assertTrue(outcome["ok"])
        target.refresh_from_db()
        self.assertFalse(device_trust_valid(self._request(token), target))

    def test_operator_explicit_session_revocation_revokes_trust(self):
        actor = User.objects.create_user(
            username=f"trust-session-actor-{uuid.uuid4().hex[:8]}",
            password="Trust-Actor-2026!",
            is_staff=True,
            is_superuser=True,
        )
        target = User.objects.create_user(
            username=f"trust-session-target-{uuid.uuid4().hex[:8]}",
            password="Trust-Operator-2026!",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        ensure_platform_operator_profile(actor, tier="break_glass")
        ensure_platform_operator_profile(target, tier="support")
        token = issue_device_trust_token(target)

        outcome = bulk_apply_operator_team_actions(
            user_ids=[target.pk],
            action="revoke_sessions",
            actor=actor,
        )
        self.assertTrue(outcome["ok"])
        target.refresh_from_db()
        self.assertFalse(device_trust_valid(self._request(token), target))
