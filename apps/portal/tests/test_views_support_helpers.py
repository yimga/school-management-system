from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.portal.views_support import support_request


class SupportRequestHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_support_request_continues_when_global_ticket_side_effect_fails(self):
        request = self.factory.post(
            "/portal/support/",
            data={
                "category": "support",
                "subject": "Need help",
                "message": "Please assist",
            },
        )
        request.user = SimpleNamespace(
            is_authenticated=True,
            get_full_name=lambda: "Test User",
            username="tester",
            role="ADMIN",
            email="test@example.com",
        )
        request.school = object()
        request._messages = MagicMock()
        request.session = {}

        with patch("apps.portal.views_support._pick_support_owner", return_value=None):
            with patch("apps.portal.views_support.render") as render_mock:
                with patch("apps.portal.views_support.redirect") as redirect_mock:
                    with patch("apps.portal.views_support.messages.success"):
                        with patch(
                            "apps.portal.views_support.SupportRequestForm"
                        ) as form_cls:
                            form = form_cls.return_value
                            form.is_valid.return_value = True
                            form.cleaned_data = {
                                "category": "SUPPORT",
                                "subject": "Need help",
                                "message": "Please assist",
                            }
                            with patch(
                                "apps.portal.runtime_helpers.get_policy_for_request",
                                return_value={"plan_slug": "pro", "country_code": "US"},
                            ):
                                with patch(
                                    "apps.siteconfig.models_feature_controls.GlobalSupportTicket.objects.create",
                                    side_effect=AttributeError,
                                ):
                                    support_request(request)

        redirect_mock.assert_called_once()
        render_mock.assert_not_called()
