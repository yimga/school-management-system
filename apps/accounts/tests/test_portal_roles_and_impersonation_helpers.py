import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.portal_roles import ACTIVE_PORTAL_ROLE_KEY, get_effective_portal_role
from apps.accounts.views_impersonation import _parse_impersonation_token


class PortalRoleHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_get_effective_portal_role_falls_back_to_user_role_when_preference_lookup_fails(
        self,
    ):
        request = self.factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True, role="PARENT")
        request.session = {}
        request._portal_teacher_hat = True
        request._portal_parent_hat = True

        with patch(
            "apps.accounts.portal_roles.get_effective_site_settings",
            side_effect=AttributeError,
        ):
            self.assertEqual(get_effective_portal_role(request), "PARENT")
            self.assertNotIn(ACTIVE_PORTAL_ROLE_KEY, request.session)


class ImpersonationTokenHelperTests(SimpleTestCase):
    def test_parse_impersonation_token_returns_none_for_invalid_payload(self):
        payload = base64.b64encode(b"not-json").decode()

        with patch(
            "apps.accounts.views_impersonation.TimestampSigner.unsign",
            return_value=payload,
        ):
            self.assertIsNone(_parse_impersonation_token("token"))

    @override_settings(IMPERSONATION_DEFAULT_READ_ONLY=True)
    def test_parse_impersonation_token_returns_payload_for_valid_token(self):
        payload = base64.b64encode(
            json.dumps({"school_id": "abc", "user_id": 42}).encode()
        ).decode()

        with patch(
            "apps.accounts.views_impersonation.TimestampSigner.unsign",
            return_value=payload,
        ):
            self.assertEqual(
                _parse_impersonation_token("token"),
                {"school_id": "abc", "user_id": 42, "read_only": True},
            )

    @override_settings(IMPERSONATION_DEFAULT_READ_ONLY=True)
    def test_parse_impersonation_token_honors_read_only_in_payload(self):
        payload = base64.b64encode(
            json.dumps(
                {"school_id": "abc", "user_id": 42, "read_only": False}
            ).encode()
        ).decode()

        with patch(
            "apps.accounts.views_impersonation.TimestampSigner.unsign",
            return_value=payload,
        ):
            self.assertEqual(
                _parse_impersonation_token("token"),
                {"school_id": "abc", "user_id": 42, "read_only": False},
            )
