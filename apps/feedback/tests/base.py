from django.contrib.auth import get_user_model
from django.test import TestCase
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.schools.models import School, SchoolMembership


User = get_user_model()


class FeedbackTestCase(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="School A", slug="feedback-a", subdomain="feedback-a", is_active=True
        )
        self.school_b = School.objects.create(
            name="School B", slug="feedback-b", subdomain="feedback-b", is_active=True
        )
        self.admin = User.objects.create_user("feedback-admin", password="password", role="ADMIN")
        self.teacher = User.objects.create_user("feedback-teacher", password="password", role="TEACHER")
        self.parent = User.objects.create_user("feedback-parent", password="password", role="PARENT")
        self.student = User.objects.create_user("feedback-student", password="password", role="STUDENT")
        self.operator = User.objects.create_user("feedback-operator", password="password", role="SUPERADMIN")
        self.operator.is_staff = True
        self.operator.save(update_fields=["is_staff"])
        for user in [self.admin, self.operator]:
            TOTPDevice.objects.get_or_create(user=user, name="test-device", confirmed=True)
        for user in [self.admin, self.teacher, self.parent, self.student]:
            SchoolMembership.objects.create(user=user, school=self.school_a, role=user.role, is_primary=True)

    def force_login_with_mfa(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()
