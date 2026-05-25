"""IAM localization — tenant cockpit_payload role/action labels."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.iam_localization import (
    localized_government_body_label,
    localized_permission_label,
    localized_role_label,
    load_iam_localization,
)


class IamLocalizationTests(SimpleTestCase):
    def test_role_label_fallback_when_no_school(self):
        self.assertEqual(localized_role_label("ADMIN", None), "Admin")

    def test_role_label_from_cockpit_block(self):
        block = {
            "role_mappings": {
                "ADMIN": {"local_display_name": "Directeur"},
            },
            "government_body_label": "MINEDUB",
        }
        school = object()
        with patch(
            "apps.accounts.iam_localization.load_iam_localization",
            return_value=block,
        ):
            self.assertEqual(
                localized_role_label("ADMIN", school, fallback="Admin"),
                "Directeur",
            )
            self.assertEqual(
                localized_government_body_label(school, default="Regulator"),
                "MINEDUB",
            )

    def test_permission_label_dot_format_fallback(self):
        self.assertIn("manage", localized_permission_label("settings.manage", None).lower())

    def test_load_iam_localization_empty_without_site(self):
        self.assertEqual(load_iam_localization(None), {})
