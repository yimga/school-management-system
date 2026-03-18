from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.communication.views_announcements import _get_announcement_feature_flags


class AnnouncementFlagHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_get_announcement_feature_flags_falls_back_when_policy_lookup_fails(self):
        request = self.factory.get("/")
        request.school = object()

        with patch(
            "apps.communication.views_announcements.get_effective_flags",
            return_value={},
        ):
            with patch(
                "apps.communication.views_announcements.default_announcement_submit_for_approval_roles",
                return_value=["TEACHER"],
            ):
                with patch(
                    "apps.policies.policy_registry.get_effective_policy",
                    side_effect=AttributeError,
                ):
                    flags = _get_announcement_feature_flags(request)

        self.assertEqual(flags["submit_for_approval_roles"], ["TEACHER"])
        self.assertFalse(flags["allow_submit_for_approval"])

    def test_get_announcement_feature_flags_uses_default_when_flag_resolution_fails(
        self,
    ):
        request = self.factory.get("/")

        with patch(
            "apps.communication.views_announcements.get_effective_flags",
            side_effect=TypeError,
        ):
            with patch(
                "apps.communication.views_announcements.default_announcement_submit_for_approval_roles",
                return_value=["COMMS_STAFF"],
            ):
                flags = _get_announcement_feature_flags(request)

        self.assertEqual(flags["submit_for_approval_roles"], ["COMMS_STAFF"])
        self.assertFalse(flags["allow_submit_for_approval"])
