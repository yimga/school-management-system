import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.schools.models import School, SchoolMembership


User = get_user_model()


def _trim_middleware_for_feedback_tests():
    """Minimal tenant HTTP stack — enough for urlconf + school + MFA without audit lock flake."""
    return [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "apps.schools.middleware.UrlConfSwitcherMiddleware",
        "apps.schools.middleware.TenantMiddleware",
        "apps.schools.middleware_session_school_bind.SessionSchoolBindingMiddleware",
        "apps.platform_runtime.middleware.TenantRuntimeMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django_otp.middleware.OTPMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "apps.accounts.middleware.RequireMFAMiddleware",
    ]


_FEEDBACK_TEST_SETTINGS = dict(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SESSION_PINNING_ENABLED=False,
    ALLOWED_HOSTS=["*"],
    DISABLE_SCHOOL_ACTIVATION_GATE=True,
    SESSION_COOKIE_DOMAIN=None,
    CSRF_COOKIE_DOMAIN=None,
    MIDDLEWARE=_trim_middleware_for_feedback_tests(),
)


class _FeedbackClientMixin:
    """Shared tenant-host client setup for feedback HTTP contract tests."""

    @classmethod
    def setUpTestData(cls):
        suffix = uuid.uuid4().hex[:8]
        cls.school_a = School.objects.create(
            name="School A",
            slug=f"feedback-a-{suffix}",
            subdomain=f"feedback-a-{suffix}",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="School B",
            slug=f"feedback-b-{suffix}",
            subdomain=f"feedback-b-{suffix}",
            is_active=True,
        )
        cls.admin = User.objects.create_user(
            f"feedback-admin-{suffix}", password="password", role="ADMIN"
        )
        cls.teacher = User.objects.create_user(
            f"feedback-teacher-{suffix}", password="password", role="TEACHER"
        )
        cls.parent = User.objects.create_user(
            f"feedback-parent-{suffix}", password="password", role="PARENT"
        )
        cls.student = User.objects.create_user(
            f"feedback-student-{suffix}", password="password", role="STUDENT"
        )
        cls.operator = User.objects.create_user(
            f"feedback-operator-{suffix}",
            password="password",
            role="SUPERADMIN",
            is_staff=True,
            is_superuser=True,
        )
        for user in (cls.admin, cls.teacher, cls.operator):
            TOTPDevice.objects.get_or_create(
                user=user, name="test-device", defaults={"confirmed": True}
            )
        for user in (cls.admin, cls.teacher, cls.parent, cls.student):
            SchoolMembership.objects.create(
                user=user, school=cls.school_a, role=user.role, is_primary=True
            )

    def setUp(self):
        self.default_host = f"{self.school_a.subdomain}.runmycampus.com"
        self.client = Client(HTTP_HOST=self.default_host)

    def force_login_with_mfa(self, user, *, password: str = "password"):
        if not self.client.login(username=user.username, password=password):
            self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        session = self.client.session
        session["mfa_verified"] = True
        session["mfa_verified_until"] = (
            timezone.now() + timezone.timedelta(hours=2)
        ).isoformat()
        session.save()


@override_settings(**_FEEDBACK_TEST_SETTINGS)
class FeedbackTestCase(_FeedbackClientMixin, TransactionTestCase):
    pass


@override_settings(**_FEEDBACK_TEST_SETTINGS)
class FeedbackHelpCenterTestCase(_FeedbackClientMixin, TestCase):
    """Help Center contracts — TestCase (atomic) for reliable gate DB reuse on Windows."""
