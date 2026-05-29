"""Phase 3C — context profile session + model tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.governance.context_profiles import (
    ACTIVE_PROFILE_SESSION_KEY,
    list_profiles,
    resolve_active_profile,
    set_active_profile_session,
)
from apps.governance.models import Organization, SchoolContextProfile
from apps.schools.models import School

User = get_user_model()


class ContextProfileServiceTests(SimpleTestCase):
    def test_anonymous_user_gets_empty_profile_list(self):
        self.assertEqual(list_profiles(None).count(), 0)

    def test_resolve_active_profile_from_session(self):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = MagicMock(is_authenticated=True, pk=42)
        request.session = {ACTIVE_PROFILE_SESSION_KEY: "7"}

        profile = MagicMock(pk=7)
        with patch(
            "apps.governance.context_profiles.SchoolContextProfile.objects.filter",
        ) as mock_filter:
            mock_filter.return_value.select_related.return_value.first.return_value = profile
            resolved = resolve_active_profile(request)

        self.assertIs(resolved, profile)
        mock_filter.assert_called_with(pk=7, user=request.user)


class SchoolContextProfileModelTests(TestCase):
    def test_unique_user_school_context_key(self):
        org = Organization.objects.create(name="Trust", slug="trust-ctx")
        school = School.objects.create(
            name="Campus A",
            slug="campus-a-ctx",
            subdomain="campus-a-ctx",
            organization=org,
        )
        user = User.objects.create_user(username="dual-role", password="Test1234!")
        SchoolContextProfile.objects.create(
            user=user,
            school=school,
            role=User.Role.TEACHER,
            context_key="teacher",
            label="Teaching",
        )
        SchoolContextProfile.objects.create(
            user=user,
            school=school,
            role=User.Role.PARENT,
            context_key="parent",
            label="Parent view",
            is_default=True,
        )
        self.assertEqual(SchoolContextProfile.objects.filter(user=user).count(), 2)

    def test_set_active_profile_session_persists_key(self):
        school = School.objects.create(
            name="Campus B",
            slug="campus-b-ctx",
            subdomain="campus-b-ctx",
        )
        user = User.objects.create_user(username="ctx-user", password="Test1234!")
        profile = SchoolContextProfile.objects.create(
            user=user,
            school=school,
            role=User.Role.TEACHER,
            context_key="teacher",
            label="Teacher",
        )
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user
        session = {}
        request.session = session

        set_active_profile_session(request, profile.pk)
        self.assertEqual(session[ACTIVE_PROFILE_SESSION_KEY], profile.pk)
