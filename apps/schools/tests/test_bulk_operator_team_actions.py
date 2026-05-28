"""Bulk operator team action service tests."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.platform_runtime.models_operator_identity import PlatformOperatorProfile
from apps.platform_runtime.operator_identity import ensure_platform_operator_profile
from apps.schools.bulk_operator_team_actions import bulk_apply_operator_team_actions

User = get_user_model()


class BulkOperatorTeamActionsTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            username=f"bulk_team_actor_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        ensure_platform_operator_profile(self.actor, tier="break_glass")
        self.target = User.objects.create_user(
            username=f"bulk_team_target_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        ensure_platform_operator_profile(self.target, tier="support")
        PlatformOperatorProfile.objects.filter(user=self.target).update(
            status=PlatformOperatorProfile.Status.ACTIVE
        )

    def test_suspend_and_reactivate(self):
        outcome = bulk_apply_operator_team_actions(
            user_ids=[self.target.pk],
            action="suspend",
            actor=self.actor,
        )
        self.assertTrue(outcome["ok"])
        profile = PlatformOperatorProfile.objects.get(user=self.target)
        self.assertEqual(profile.status, PlatformOperatorProfile.Status.SUSPENDED)

        outcome = bulk_apply_operator_team_actions(
            user_ids=[self.target.pk],
            action="reactivate",
            actor=self.actor,
        )
        self.assertTrue(outcome["ok"])
        profile.refresh_from_db()
        self.assertEqual(profile.status, PlatformOperatorProfile.Status.ACTIVE)

    def test_set_tier_requires_confirm_phrase(self):
        with self.assertRaises(ValueError):
            bulk_apply_operator_team_actions(
                user_ids=[self.target.pk],
                action="set_tier",
                actor=self.actor,
                tier="security",
                confirm_phrase="wrong",
            )

    def test_set_tier_with_phrase(self):
        outcome = bulk_apply_operator_team_actions(
            user_ids=[self.target.pk],
            action="set_tier",
            actor=self.actor,
            tier="security",
            confirm_phrase="SET OPERATOR TIER",
        )
        self.assertTrue(outcome["ok"])
        profile = PlatformOperatorProfile.objects.get(user=self.target)
        self.assertEqual(profile.tier, "security")
