"""HMAC session school binding."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.schools.middleware_session_school_bind import SessionSchoolBindingMiddleware
from apps.schools.models import School, SchoolMembership
from apps.schools.session_school_bind import (
    sign_session_school_bind,
    verify_session_school_bind,
)


class SessionSchoolBindTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(
            name="Bind School",
            slug="bind-school",
            subdomain="bindschool",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="bind_user",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )

    def test_sign_and_verify_round_trip(self):
        session = {}
        sign_session_school_bind(
            session, school_id=str(self.school.pk), user_id=self.user.pk
        )
        self.assertTrue(verify_session_school_bind(session, self.user))

    def test_tampered_session_fails_verify(self):
        session = {}
        sign_session_school_bind(
            session, school_id=str(self.school.pk), user_id=self.user.pk
        )
        session["school_id"] = "00000000-0000-0000-0000-000000000099"
        self.assertFalse(verify_session_school_bind(session, self.user))
