"""The backend dashboard must survive a urlconf that mounts no admin site.

``AdminSite.each_context`` builds ``available_apps``, and Django's ``_build_app_dict``
reverses ``admin:app_list`` once per app while doing it. On a host whose urlconf mounts
no admin site that reverse raises -- from INSIDE ``each_context``, which is why the
guarded ``reverse("admin:index")`` twenty lines further down (added for exactly this
failure, with a comment saying so) never got the chance to run.

That is how http://<box-ip>:10000/authentication/backend/ returned 500 instead of a
dashboard: a sovereign box was served ``config.urls``, which mounts neither admin site.
The host routing is fixed separately (``test_edge_box_urlconf_2026_08_22``); this is the
belt to that braces. The module COUNT is one hero-stat, and losing it must never cost
the whole page.
"""
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import NoReverseMatch
from django_otp.plugins.otp_totp.models import TOTPDevice

from django.contrib.auth import get_user_model

from apps.schools.models import School, SchoolMembership

User = get_user_model()
HOST = "gilead.school.lan"


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="school.lan",
    SINGLE_TENANT=False,
    USE_DJANGO_TENANTS=False,
)
class BackendDashboardSurvivesMissingAdminTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Gilead Tech High", slug="gilead", subdomain="gilead", is_active=True
        )
        self.user = User.objects.create_superuser(
            username="boxadmin", email="box@example.com", password="x" * 16
        )
        SchoolMembership.objects.get_or_create(user=self.user, school=self.school)
        TOTPDevice.objects.get_or_create(
            user=self.user, name="default", defaults={"confirmed": True}
        )
        self.client = self.client_class(HTTP_HOST=HOST)
        self.client.force_login(self.user)
        session = self.client.session
        session["mfa_verified"] = True
        session["school_id"] = str(self.school.id)
        session.save()

    def test_dashboard_renders_when_each_context_cannot_reverse_the_admin(self):
        from apps.accounts import views

        with mock.patch.object(
            views.admin_site,
            "each_context",
            side_effect=NoReverseMatch("'admin' is not a registered namespace"),
        ):
            response = self.client.get("/authentication/backend/")
        # Before the guard this was an uncaught NoReverseMatch -> 500.
        self.assertEqual(response.status_code, 200, response.get("Location", ""))

    def test_dashboard_still_renders_normally(self):
        response = self.client.get("/authentication/backend/")
        self.assertEqual(response.status_code, 200, response.get("Location", ""))
