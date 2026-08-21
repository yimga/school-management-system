"""The API Center used to answer every refusal with the same wrong sentence.

Thirteen call sites returned::

    "API Center is disabled or you do not have permission."

which covers a tenant CONFIGURATION fact and a MISSING GRANT in one breath. The
two are not the same kind of no. A feature switch answers "does this school have
this surface at all"; a permission answers "may this person use it". For a
platform superadmin — who holds every permission code there is — the second half
of that sentence was not merely unhelpful, it was false.

The fix is not to let god-mode override the tenant's switch. A superuser
flipping a customer's configuration by walking into a page is a product change,
not an access grant. The fix is to say which of the two actually happened, and
to hand the switch to whoever can flip it.

Authority is now resolved BEFORE the flag, which is a security ordering as much
as a wording one: someone with no business on the surface no longer learns
whether the school has it turned on.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import AccessRole, Permission, User
from apps.apicenter.views import (
    API_CENTER_DENY_CONTROL_PLANE,
    API_CENTER_DENY_DISABLED,
    API_CENTER_DENY_PERMISSION,
    API_CENTER_OK,
    _api_center_denial_reason,
)
from apps.schools.models import School

FLAGS_ON = {"enable_api_center": True}
FLAGS_OFF = {"enable_api_center": False}


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@override_settings(ALLOWED_HOSTS=["*"])
class TheRefusalNamesItsOwnReasonTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name=_unique("Sch"),
            slug=_unique("s"),
            subdomain=_unique("sd"),
            is_active=True,
        )

    def _request(self, user, *, host_kind=None):
        request = self.factory.get("/backend/api-center/")
        request.user = user
        request.school = self.school
        request.public_host_kind = host_kind
        return request

    def _reason(self, user, flags, *, host_kind=None):
        with patch("apps.apicenter.views.get_effective_flags", return_value=flags):
            return _api_center_denial_reason(self._request(user, host_kind=host_kind))

    def _user(self, **kwargs):
        return User.objects.create_user(
            username=_unique("u"), password="Test1234", **kwargs
        )

    # --- the bug, stated as a test ------------------------------------------

    def test_a_superuser_on_a_school_with_the_switch_off_is_not_a_permission_problem(
        self,
    ):
        """The exact case that told platform root it lacked permission."""
        user = self._user(role=User.Role.PARENT, is_superuser=True)
        self.assertEqual(
            self._reason(user, FLAGS_OFF), API_CENTER_DENY_DISABLED
        )

    def test_the_superadmin_role_alone_reads_the_same_way(self):
        """God-mode is the platform role too, not only Django's flag."""
        role, _ = AccessRole.objects.get_or_create(
            code="SUPERADMIN", school=None, defaults={"name": "Super Administrator"}
        )
        role.permissions.add(*Permission.objects.all())
        user = self._user(role=User.Role.TEACHER)
        user.roles.add(role)
        self.assertEqual(self._reason(user, FLAGS_OFF), API_CENTER_DENY_DISABLED)

    # --- and the gate still bites -------------------------------------------

    def test_a_teacher_is_refused_on_permission_even_when_the_switch_is_on(self):
        user = self._user(role=User.Role.TEACHER)
        self.assertEqual(self._reason(user, FLAGS_ON), API_CENTER_DENY_PERMISSION)

    def test_a_teacher_is_told_about_permission_not_about_the_tenant_switch(self):
        """Authority first: the school's configuration is not leaked downward."""
        user = self._user(role=User.Role.TEACHER)
        self.assertEqual(self._reason(user, FLAGS_OFF), API_CENTER_DENY_PERMISSION)

    def test_an_admin_with_the_switch_on_is_allowed(self):
        user = self._user(role=User.Role.ADMIN)
        self.assertEqual(self._reason(user, FLAGS_ON), API_CENTER_OK)

    def test_an_it_admin_with_the_switch_on_is_allowed(self):
        user = self._user(role=User.Role.IT_ADMIN)
        self.assertEqual(self._reason(user, FLAGS_ON), API_CENTER_OK)

    def test_the_tenant_switch_still_wins_over_god_mode(self):
        """A superuser does NOT silently turn a customer's feature on."""
        user = self._user(role=User.Role.PARENT, is_superuser=True)
        self.assertNotEqual(self._reason(user, FLAGS_OFF), API_CENTER_OK)

    def test_the_manager_host_refuses_a_non_operator_on_its_own_terms(self):
        user = self._user(role=User.Role.TEACHER)
        self.assertEqual(
            self._reason(user, FLAGS_OFF, host_kind="manager"),
            API_CENTER_DENY_CONTROL_PLANE,
        )

    def test_the_manager_host_ignores_the_tenant_switch_for_an_operator(self):
        user = self._user(role=User.Role.PARENT, is_superuser=True)
        self.assertEqual(
            self._reason(user, FLAGS_OFF, host_kind="manager"), API_CENTER_OK
        )


class TheWordingItselfTests(TestCase):
    """The sentence is the deliverable, so assert the sentence."""

    def _template(self) -> str:
        from pathlib import Path

        return Path("templates/apicenter/api_center_unavailable.html").read_text(
            encoding="utf-8"
        )

    def test_the_disabled_case_says_the_school_has_not_enabled_it(self):
        self.assertIn("has not enabled the API Center", self._template())

    def test_the_disabled_case_offers_the_switch(self):
        body = self._template()
        self.assertIn("feature_control_url", body)
        self.assertIn("Turn it on in Feature Control", body)

    def test_the_old_conflated_sentence_is_gone_from_the_views(self):
        from pathlib import Path

        src = Path("apps/apicenter/views.py").read_text(encoding="utf-8")
        offending = [
            line
            for line in src.splitlines()
            if "API Center is disabled or you do not have permission" in line
            and not line.lstrip().startswith("#")
        ]
        self.assertEqual(offending, [], "the conflated refusal is still being returned")

    def test_every_call_site_goes_through_the_reason_aware_refusal(self):
        from pathlib import Path

        src = Path("apps/apicenter/views.py").read_text(encoding="utf-8")
        self.assertEqual(
            src.count("if not _api_center_allowed(request):"),
            src.count("return _api_center_denied(request)"),
            "a gate is refusing without going through _api_center_denied",
        )
