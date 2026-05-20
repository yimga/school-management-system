from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.people.models import TeacherProfile
from apps.siteconfig.models_dashboard import DashboardUserPreference
from apps.siteconfig.models_tooling import UserPreference
from apps.siteconfig.user_identity import (
    ensure_user_identity,
    ensure_user_portal_preferences,
    resolve_school_for_user,
)

User = get_user_model()


class UserIdentityBootstrapTests(TestCase):
    def test_ensure_portal_preferences_creates_rows(self):
        user = User.objects.create_user(username="id_pref", password="x")
        self.assertFalse(UserPreference.objects.filter(user=user).exists())
        self.assertFalse(DashboardUserPreference.objects.filter(user=user).exists())
        ensure_user_portal_preferences(user)
        self.assertTrue(UserPreference.objects.filter(user=user).exists())
        self.assertTrue(DashboardUserPreference.objects.filter(user=user).exists())

    def test_superadmin_gets_preferences_without_teacher_profile(self):
        user = User.objects.create_user(
            username="id_super",
            password="x",
            role=User.Role.SUPERADMIN,
        )
        identity = ensure_user_identity(user)
        self.assertIsNotNone(identity["portal_preference"])
        self.assertIsNone(identity["people_profile"])
        self.assertFalse(TeacherProfile.objects.filter(user=user).exists())

    def test_teacher_gets_teacher_profile_stub(self):
        user = User.objects.create_user(
            username="id_teacher",
            password="x",
            role=User.Role.TEACHER,
        )
        identity = ensure_user_identity(user)
        self.assertIsNotNone(identity["people_profile"])
        self.assertTrue(TeacherProfile.objects.filter(user=user).exists())

    def test_resolve_school_without_profile_returns_none(self):
        user = User.objects.create_user(
            username="id_noschool",
            password="x",
            role=User.Role.SUPERADMIN,
        )
        request = RequestFactory().get("/")
        request.school = None
        self.assertIsNone(resolve_school_for_user(user, request=request))
