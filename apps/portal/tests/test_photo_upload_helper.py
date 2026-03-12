from unittest.mock import patch

from django.test import TestCase

from apps.portal.views_photo_upload import _photo_upload_remote_enabled


class PhotoUploadHelperTests(TestCase):
    def test_photo_upload_remote_enabled_uses_owner_scoped_feature_control_settings(self):
        site = type(
            "Site",
            (),
            {
                "get_feature_control_settings": lambda self: {
                    "portal_features": {"photo_upload_remote": False}
                }
            },
        )()

        with patch(
            "apps.portal.views_photo_upload.get_effective_site_settings",
            return_value=site,
        ):
            self.assertFalse(_photo_upload_remote_enabled())
