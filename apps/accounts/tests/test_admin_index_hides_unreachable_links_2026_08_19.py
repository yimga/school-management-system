"""A control that exists only to refuse you is worse than no control.

Reported: a branded 403 "Access needs approval" on the Accounts User Changelist, reached
from inside the admin. ``templates/admin/index.html`` rendered nine hardcoded links — a
"Users" button to ``admin:accounts_user_changelist`` and eight "Open" buttons to
``admin:app_list`` — with **zero** permission checks anywhere in the file. Django's admin
then correctly refuses, so each button was a guaranteed 403 for a viewer lacking the
matching permission. The refusal was working; the invitation to be refused was the bug.

WHAT THE AUDIT ACTUALLY FOUND, because it changes what this test can honestly claim: on a
TENANT host the Django admin is operator-only. A school-role staff user is refused at
``/admin/`` itself (403) even holding real model permissions — that is the deliberate
tenant/operator isolation posture (``scan_staff_gate_on_tenant_surface``,
``TenantSuperAdminRequiredMiddleware``), and the reported 403 is therefore the system
working. The ungated buttons still matter on the OPERATOR host, where non-superuser
operators with partial permissions are exactly who this page serves.

So the gate is asserted two ways, neither of which pretends to be an end-to-end tenant
render it cannot produce:

  * a CONTRACT test over the template source — no ``{% url 'admin:… %}`` may sit outside a
    ``perms.`` guard — which is the durable seal and catches the next ungated link someone
    adds; and
  * a real render as a superuser, proving the gate does not hide the page from the people
    it is for (the failure mode of "just require superuser everywhere").
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership

_URLCONF = "config.tenant_urls"
_TEMPLATE = Path(settings.BASE_DIR) / "templates" / "admin" / "index.html"

_ADMIN_URL_TAG = re.compile(r"\{%\s*url\s+'admin:[^']+'[^%]*%\}")
_PERMS_GUARD = re.compile(r"\{%\s*if\s+[^%]*\bperms\.")


# The MFA ENROLMENT gate redirects a device-less principal before the page renders, so
# the render assertion below would land on that redirect instead of the admin index.
_MW = [
    m for m in settings.MIDDLEWARE
    if "RequireMFAMiddleware" not in m and "OperatorMfaRequiredMiddleware" not in m
]


def _url(name, *args):
    return reverse(name, args=list(args) or None, urlconf=_URLCONF)


class AdminIndexLinkGatingContractTests(TestCase):
    """The seal: an admin link on this page must be inside a permission guard."""

    def test_every_admin_link_on_the_index_sits_inside_a_perms_guard(self):
        lines = _TEMPLATE.read_text(encoding="utf8").splitlines()
        ungated = []
        for i, line in enumerate(lines, 1):
            if not _ADMIN_URL_TAG.search(line):
                continue
            # The guard may open on this line or on the line above it.
            window = line + "\n" + (lines[i - 2] if i >= 2 else "")
            if not _PERMS_GUARD.search(window):
                ungated.append(f"L{i}: {line.strip()[:100]}")
        self.assertEqual(
            ungated,
            [],
            "admin links rendered without a perms guard always 403 for a viewer who "
            "lacks the permission:\n  " + "\n  ".join(ungated),
        )

    def test_the_page_still_offers_links_at_all(self):
        """Guards against the lazy 'fix' of deleting the buttons instead of gating them —
        which would make the contract test above pass while removing the feature."""
        source = _TEMPLATE.read_text(encoding="utf8")
        self.assertGreaterEqual(
            len(_ADMIN_URL_TAG.findall(source)),
            9,
            "the admin links were removed rather than gated",
        )

    def test_the_guards_name_the_app_each_link_targets(self):
        """A blanket `{% if perms %}` would satisfy the contract test while still offering
        every viewer every button. Each app_list link must be guarded on ITS app."""
        source = _TEMPLATE.read_text(encoding="utf8")
        for app in ("academics", "evals", "reports", "finance", "payroll",
                    "portal", "analytics", "compliance"):
            self.assertIn(
                f"{{% if perms.{app} %}}",
                source,
                f"the {app} button is not guarded on perms.{app}",
            )
        self.assertIn("{% if perms.accounts.view_user %}", source)


@override_settings(ROOT_URLCONF=_URLCONF, MIDDLEWARE=_MW)
class AdminIndexStillRendersForItsAudienceTests(TestCase):
    """The gate must not hide the page from the people it is for."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Perm {uid}", slug=f"perm-{uid}",
            subdomain=f"perm{uid}", is_active=True,
        )
        self.root = User.objects.create_superuser(
            username=f"root_{uid}", password="Test1234!x", email=f"r{uid}@test.com",
        )
        SchoolMembership.objects.create(
            user=self.root, school=self.school, role="ADMIN", is_primary=True
        )

    def test_a_superuser_sees_the_users_button(self):
        self.client.force_login(self.root)
        session = self.client.session
        session["mfa_verified"] = True
        session["school_id"] = str(self.school.id)
        session.save()
        resp = self.client.get(
            _url("admin:index"), HTTP_HOST=f"{self.school.subdomain}.runmycampus.com"
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf8")
        self.assertIn(_url("admin:accounts_user_changelist"), html)
        self.assertIn(_url("admin:app_list", "finance"), html)
