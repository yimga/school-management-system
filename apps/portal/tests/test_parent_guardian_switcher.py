"""CEZGP batch 1517 — parent identity UX."""

from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.portal.parent_identity import (
    resolve_parent_simplified_default,
    school_membership_switch_context,
)
class ParentSimplifiedDefaultTests(SimpleTestCase):
    def test_default_on_without_query(self):
        from unittest.mock import patch

        rf = RequestFactory()
        request = rf.get("/parent/")
        request.user = User(username="p", role=User.Role.PARENT)
        with patch(
            "apps.portal.parent_identity.get_effective_flags",
            return_value={"parent_simplified_default_home": True},
        ):
            self.assertTrue(resolve_parent_simplified_default(request))

    def test_simple_zero_disables(self):
        from unittest.mock import patch

        rf = RequestFactory()
        request = rf.get("/parent/?simple=0")
        request.user = User(username="p", role=User.Role.PARENT)
        with patch(
            "apps.portal.parent_identity.get_effective_flags",
            return_value={"parent_simplified_default_home": True},
        ):
            self.assertFalse(resolve_parent_simplified_default(request))


class SchoolMembershipSwitchTests(SimpleTestCase):
    def test_multi_school_enables_switcher(self):
        from unittest.mock import MagicMock, patch

        user = MagicMock()
        user.role = User.Role.PARENT
        user.is_authenticated = True
        rf = RequestFactory()
        request = rf.get("/parent/")
        request.user = user
        mock_qs = MagicMock()
        mock_qs.count.return_value = 2
        with patch(
            "apps.schools.models.SchoolMembership.objects.filter",
            return_value=mock_qs,
        ):
            ctx = school_membership_switch_context(request)
        self.assertTrue(ctx["school_membership_switch"]["enabled"])
        self.assertEqual(ctx["school_membership_switch"]["count"], 2)


class ParentSettingsSecurityContractTests(SimpleTestCase):
    def test_settings_security_url_and_template(self):
        from pathlib import Path

        url = reverse("portal:parent_settings_security")
        self.assertIn("settings/security", url)
        tpl = (
            Path(__file__).resolve().parents[3]
            / "templates"
            / "parent"
            / "settings_security.html"
        )
        body = tpl.read_text(encoding="utf-8")
        self.assertIn("passkey", body.lower())
