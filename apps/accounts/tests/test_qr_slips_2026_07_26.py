"""Printable QR access slips for join codes (Feature 4)."""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.join_codes import generate_join_code
from apps.accounts.qr_slips import join_code_join_url, qr_png_data_uri
from apps.schools.models import School


class QrSlipTests(TestCase):
    def test_qr_png_data_uri_is_self_contained_png(self):
        uri = qr_png_data_uri("https://gilead-tech.example/authentication/join/?code=ABCD2345")
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertGreater(len(uri), 200)

    def test_join_code_join_url_carries_the_code(self):
        school = School.objects.create(
            name="Gilead", slug="gilead-tech", subdomain="gilead-tech", is_active=True
        )
        jc = generate_join_code(school=school, role="PARENT")
        url = join_code_join_url(jc)
        self.assertIn("join", url)
        self.assertIn(f"code={jc.code}", url)
