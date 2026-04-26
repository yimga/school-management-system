"""Wave B: CSRF-exempt WOPI entrypoints are gated by per-document access_token (defense in depth)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.portal.models_kb import HostedOfficeDocument


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class WopiCsrfExemptTokenGateTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.doc = HostedOfficeDocument.objects.create(
            title="WOPI gate doc",
            file=SimpleUploadedFile(
                "wopi_gate.txt", b"hello wopi", content_type="text/plain"
            ),
        )

    def setUp(self):
        self.client = Client()

    def test_wopi_check_file_info_403_without_valid_token(self) -> None:
        url = reverse("kb:wopi_check_file_info", args=[self.doc.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403, msg=resp.content)
