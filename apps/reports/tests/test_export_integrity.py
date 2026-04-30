from django.conf import settings
from django.test import TestCase

from apps.reports.export_integrity import (
    attach_export_integrity_headers,
    sign_export_content,
    verify_export_signature,
)


class ExportIntegrityTests(TestCase):
    def test_sign_and_verify_round_trip(self):
        content = b"col1,col2\n1,2\n"
        secret = "test-secret-key"
        sha, sig, _ver = sign_export_content(
            content,
            export_key="test_export",
            school_id="uuid-1",
            secret=secret,
        )
        self.assertEqual(len(sha), 64)
        from django.http import HttpResponse

        r = HttpResponse(content)
        attach_export_integrity_headers(
            r,
            content=content,
            export_key="test_export",
            school_id="uuid-1",
            secret=secret,
        )
        self.assertEqual(r["X-Export-Content-SHA256"], sha)
        sig_val = (r["X-Export-Signature"] or "").split("=", 1)[-1]
        self.assertTrue(
            verify_export_signature(
                content,
                export_key="test_export",
                school_id="uuid-1",
                secret=secret,
                signature_hex=sig_val,
            )
        )

    def test_tamper_fails_verify(self):
        content = b"x"
        secret = settings.SECRET_KEY
        _sha, _sig, _v = sign_export_content(
            content,
            export_key="k",
            school_id="s",
            secret=secret,
        )
        self.assertFalse(
            verify_export_signature(
                b"y",
                export_key="k",
                school_id="s",
                secret=secret,
                signature_hex=_sig,
            )
        )
