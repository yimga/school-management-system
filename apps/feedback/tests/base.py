import uuid

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.schools.models import School, SchoolMembership


User = get_user_model()


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
)
class FeedbackTestCase(TransactionTestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex[:8]
        self.school_a = School.objects.create(
            name="School A",
            slug=f"feedback-a-{suffix}",
            subdomain=f"feedback-a-{suffix}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="School B",
            slug=f"feedback-b-{suffix}",
            subdomain=f"feedback-b-{suffix}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            f"feedback-admin-{suffix}", password="password", role="ADMIN"
        )
        self.teacher = User.objects.create_user(
            f"feedback-teacher-{suffix}", password="password", role="TEACHER"
        )
        self.parent = User.objects.create_user(
            f"feedback-parent-{suffix}", password="password", role="PARENT"
        )
        self.student = User.objects.create_user(
            f"feedback-student-{suffix}", password="password", role="STUDENT"
        )
        self.operator = User.objects.create_user(
            f"feedback-operator-{suffix}",
            password="password",
            role="SUPERADMIN",
            is_staff=True,
            is_superuser=True,
        )
        for user in [self.admin, self.operator]:
            TOTPDevice.objects.get_or_create(user=user, name="test-device", confirmed=True)
        for user in [self.admin, self.teacher, self.parent, self.student]:
            SchoolMembership.objects.create(user=user, school=self.school_a, role=user.role, is_primary=True)

    def force_login_with_mfa(self, user, *, password: str = "password"):
        self.client.login(username=user.username, password=password)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()
