"""An Add button that only ever refuses you is worse than no Add button.

Every backend create view is gated with
``@permission_required("<app>.add_<model>", raise_exception=True)``, so a user
holding ``view_*`` but not ``add_*`` could reach the list, see a primary "Add"
button, click it and receive a hard 403.  The button was rendered
unconditionally -- there was no ``perms`` guard anywhere in the seven list
templates -- so the refusal was working and the invitation to be refused was
the defect.

The same guard is what makes the surface honestly RBAC-driven: the control is
present exactly when the person can use it.

Gating is safe because the ADMIN role holds every one of these permissions
(measured: 243 model permissions, including all seven ``add_*``), while TEACHER
and PARENT hold zero -- so no role that could previously act loses the button.

These tests RENDER the pages for two principals that differ only in their
permissions.  A source assertion would not do: both users get HTTP 200 on every
list, so only the presence of the anchor separates gated from ungated.
"""
from __future__ import annotations

import re
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership

_URLCONF = "config.tenant_urls"

# The MFA ENROLMENT gate redirects a device-less principal before the list
# renders, so the assertions below would land on that redirect instead.
_MW = [
    m
    for m in settings.MIDDLEWARE
    if "RequireMFAMiddleware" not in m and "OperatorMfaRequiredMiddleware" not in m
]

# list route name -> the permission its create view enforces
SURFACES = {
    "accounts:backend_student_list": "add_studentprofile",
    "accounts:backend_teacher_list": "add_teacherprofile",
    "accounts:backend_guardian_list": "add_studentguardian",
    "accounts:backend_subject_list": "add_subject",
    "accounts:backend_specialty_list": "add_specialty",
    "accounts:backend_classroom_list": "add_classroom",
    "accounts:backend_applicant_list": "add_applicant",
}

VIEW_CODENAMES = [
    "view_studentprofile",
    "view_teacherprofile",
    "view_studentguardian",
    "view_subject",
    "view_specialty",
    "view_classroom",
    "view_applicant",
]

_CREATE_ANCHOR = re.compile(r'href="(/authentication/backend/[a-z]+/create/)"')


@override_settings(ROOT_URLCONF=_URLCONF, MIDDLEWARE=_MW)
class CreateButtonFollowsThePermissionTests(TestCase):
    """The Add control appears exactly when the viewer may actually add."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"RBAC Button {uid}",
            slug=f"rbac-button-{uid}",
            subdomain=f"rbacbutton{uid}",
            is_active=True,
        )
        self.host = f"{self.school.subdomain}.runmycampus.com"

        # Can read every list, may add nothing.
        self.viewer = User.objects.create_user(
            username=f"viewer_{uid}", password="Test1234!x", email=f"v{uid}@t.com",
            role="TEACHER",
        )
        SchoolMembership.objects.create(
            user=self.viewer, school=self.school, role="TEACHER", is_primary=True
        )
        self.viewer.user_permissions.set(
            Permission.objects.filter(codename__in=VIEW_CODENAMES)
        )
        self.viewer = User.objects.get(pk=self.viewer.pk)

        self.admin = User.objects.create_user(
            username=f"admin_{uid}", password="Test1234!x", email=f"a{uid}@t.com",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN", is_primary=True
        )
        self.admin = User.objects.get(pk=self.admin.pk)

    def _client_for(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["mfa_verified"] = True
        session["school_id"] = str(self.school.id)
        session.save()
        # The security-review interstitial answers the first request of a
        # session with a 302; burn it so the assertions see the real page.
        self.client.get(
            reverse("accounts:backend_dashboard", urlconf=_URLCONF), HTTP_HOST=self.host
        )
        return self.client

    def _create_anchors(self, route):
        resp = self.client.get(
            reverse(route, urlconf=_URLCONF), HTTP_HOST=self.host
        )
        self.assertEqual(
            resp.status_code, 200, f"{route} did not render for this principal"
        )
        return set(_CREATE_ANCHOR.findall(resp.content.decode("utf8")))

    def test_a_view_only_user_is_not_offered_a_button_that_would_403(self):
        self._client_for(self.viewer)
        for route in SURFACES:
            with self.subTest(route=route):
                self.assertEqual(
                    self._create_anchors(route),
                    set(),
                    f"{route} offered an Add control to a user without the "
                    "matching add_* permission -- clicking it returns 403",
                )

    def test_an_admin_still_gets_every_button(self):
        """The failure mode of gating: hiding the control from its audience."""
        self._client_for(self.admin)
        for route in SURFACES:
            with self.subTest(route=route):
                self.assertNotEqual(
                    self._create_anchors(route),
                    set(),
                    f"{route} hid the Add control from an ADMIN who holds the "
                    "permission -- the gate is too strict",
                )

    def test_the_admin_role_actually_holds_every_gated_permission(self):
        """A gate on a permission nobody holds hides the surface forever.

        This is the check that makes the two render tests safe to trust: if the
        ADMIN role ever stops being granted one of these, the button would
        vanish platform-wide with no other test noticing.
        """
        held = {p.split(".")[-1] for p in self.admin.get_all_permissions()}
        missing = sorted(set(SURFACES.values()) - held)
        self.assertEqual(
            missing, [], f"ADMIN no longer holds: {missing} -- gating hides these"
        )
