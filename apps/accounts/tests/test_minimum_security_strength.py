"""Minimum security strength policy + evaluation flags."""

from __future__ import annotations

import uuid

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.platform_access_policy import (
    evaluation_access_flags,
    platform_baseline_minimum_score,
    user_meets_platform_security_minimum,
)
from apps.accounts.profile_security_evaluation import evaluate_user_profile_security
from apps.schools.models import School


class EvaluationFlagsTests(SimpleTestCase):
    def test_access_flags_gap(self) -> None:
        flags = evaluation_access_flags(
            {"security_score": 50, "minimum_score_for_role": 80.0}
        )
        self.assertEqual(flags["security_minimum_required"], 80)
        self.assertEqual(flags["security_minimum_gap"], 30)
        self.assertFalse(flags["meets_platform_minimum"])


class MinimumStrengthTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Min School",
            slug=f"min-{uuid.uuid4().hex[:8]}",
            subdomain=f"min-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:6]}",
            email="weak@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        User.objects.filter(pk=self.admin.pk).update(
            date_joined=timezone.now() - timedelta(days=30)
        )
        self.admin.refresh_from_db()

    def test_admin_below_role_minimum_blocked(self) -> None:
        allowed, reason, ev = user_meets_platform_security_minimum(
            self.admin, school=self.school
        )
        self.assertFalse(allowed)
        self.assertIn(reason, ("role_minimum", "platform_baseline", "below_minimum"))
        self.assertLess(int(ev.get("security_score", 0)), 80)

    def test_baseline_minimum_at_least_40(self) -> None:
        self.assertGreaterEqual(platform_baseline_minimum_score(), 40)

    def test_evaluate_includes_minimum_fields(self) -> None:
        ev = evaluate_user_profile_security(self.admin, school=self.school)
        self.assertIn("meets_platform_minimum", ev)
        self.assertIn("security_minimum_required", ev)
