"""The onboarding wizards validate profile photos by content (magic bytes).

A renamed SVG / spoofed content_type must not be storable as a served profile
photo (stored-XSS) — the same contract as the anonymous photo-upload endpoint.
Tests the shared helper `_validated_profile_photo` directly (DB-free).
"""

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase

from apps.portal.views_onboarding import _validated_profile_photo

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><script>x</script></svg>"
HTML = b"<html><body><script>alert(1)</script></body></html>"


def _request_with(upload=None):
    rf = RequestFactory()
    data = {"profile_photo": upload} if upload is not None else {}
    request = rf.post("/onboard/", data)
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class ValidatedProfilePhotoTests(SimpleTestCase):
    def test_real_png_is_returned(self):
        upload = SimpleUploadedFile("me.png", PNG, content_type="image/png")
        result = _validated_profile_photo(_request_with(upload))
        self.assertIsNotNone(result)

    def test_svg_declared_as_image_is_rejected(self):
        upload = SimpleUploadedFile("me.svg", SVG, content_type="image/svg+xml")
        request = _request_with(upload)
        self.assertIsNone(_validated_profile_photo(request))
        self.assertTrue(list(request._messages))  # a user error was surfaced

    def test_spoofed_content_type_is_rejected(self):
        upload = SimpleUploadedFile("me.png", HTML, content_type="image/png")
        self.assertIsNone(_validated_profile_photo(_request_with(upload)))

    def test_no_file_is_none(self):
        self.assertIsNone(_validated_profile_photo(_request_with(None)))
