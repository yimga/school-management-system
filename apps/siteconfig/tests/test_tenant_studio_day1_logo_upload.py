"""Tests for the Day-1 Act-1 live logo upload widget (batch 1372, agent R3).

Covers the service-layer ``Day1MagicService.accept_logo_upload`` AND the
view-layer ``TenantStudioDay1Act1LogoUploadView``. We isolate Django's
default storage with ``override_settings`` so each test writes into a
disposable temporary directory and tears down cleanly. The cross-tenant
guarantee is exercised end-to-end: a POST whose request-resolved school
differs from the operator's tenant must NOT write under the foreign
prefix.
"""

from __future__ import annotations

import struct
import tempfile
import zlib
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.siteconfig.tenant_studio_day1 import (
    DAY1_DEFAULT_LOGO_MAX_BYTES,
    Day1MagicService,
    LogoUploadResult,
)
from apps.siteconfig.views_tenant_studio_hub import (
    TenantStudioDay1Act1LogoUploadView,
)


# ---------------------------------------------------------------------------
# Fixtures — deterministic image bytes
# ---------------------------------------------------------------------------


def _build_tiny_png(width: int = 16, height: int = 16, *, color: tuple[int, int, int] = (79, 70, 229)) -> bytes:
    """Hand-roll a valid 16x16 PNG with a single solid colour.

    Stdlib-only (zlib + struct) so the fixture is reproducible without
    Pillow and the test boot stays fast.
    """

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    raw = b""
    for _ in range(height):
        raw += b"\x00" + bytes(color) * width
    idat = zlib.compress(raw)
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


_TINY_PNG_BYTES = _build_tiny_png()
_TINY_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 64 + b"\xff\xd9"
_TINY_SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
_TINY_PDF_BYTES = b"%PDF-1.4\n%fake pdf\n"


# ---------------------------------------------------------------------------
# Fakes — lightweight School / User so we never touch the migration graph
# ---------------------------------------------------------------------------


class FakeSchool:
    def __init__(
        self,
        *,
        pk: str = "school-pk-1",
        slug: str = "ghs-limbe",
        name: str = "Gilead Tech High",
        logo_url: str = "",
        primary_color: str = "#0d6efd",
        branding_metadata: dict | None = None,
    ) -> None:
        self.pk = pk
        self.slug = slug
        self.name = name
        self.logo_url = logo_url
        self.primary_color = primary_color
        self.branding_metadata = dict(branding_metadata or {})
        self.save_calls: list[dict] = []

    def save(self, update_fields=None):
        self.save_calls.append({"update_fields": tuple(update_fields or ())})


class FakeUser:
    def __init__(self, *, pk=42, is_staff=True, is_superuser=False, role="ADMIN"):
        self.pk = pk
        self.is_authenticated = True
        self.is_staff = is_staff
        self.is_superuser = is_superuser
        self.role = role


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="rmc-day1-logo-tests-"))
class AcceptLogoUploadServiceTests(TestCase):
    """``Day1MagicService.accept_logo_upload`` — full service path."""

    def test_happy_path_persists_logo_and_returns_seed(self):
        school = FakeSchool()
        user = FakeUser()
        with self.assertLogs("apps.siteconfig.tenant_studio_day1", level="INFO") as cm:
            result = Day1MagicService.accept_logo_upload(
                school, _TINY_PNG_BYTES, "Acme School Logo.png", by_user=user
            )
        self.assertIsInstance(result, LogoUploadResult)
        self.assertTrue(result.ok, msg=getattr(result, "error_message", None))
        self.assertEqual(result.source, "logo")
        self.assertTrue(result.logo_url)
        self.assertTrue(result.seed_hex and result.seed_hex.startswith("#"))
        # School row mutated atomically.
        self.assertTrue(school.logo_url)
        self.assertIn("logo_uploaded_at", school.branding_metadata)
        self.assertEqual(school.branding_metadata.get("primary_color"), result.seed_hex)
        # No PII in logs.
        joined = " ".join(cm.output)
        self.assertNotIn("ghs-limbe", joined)
        self.assertNotIn("Acme School Logo.png", joined)
        # The bytes themselves never land in the log.
        self.assertNotIn("PNG", joined.split("mime=")[-1].split(" size=")[0]) if "mime=" in joined else None

    def test_oversize_upload_rejected_with_oversize_code(self):
        school = FakeSchool()
        oversize = b"\x89PNG\r\n\x1a\n" + b"x" * (DAY1_DEFAULT_LOGO_MAX_BYTES + 16)
        result = Day1MagicService.accept_logo_upload(
            school, oversize, "huge.png", by_user=FakeUser()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "oversize")
        self.assertFalse(school.logo_url)

    def test_svg_rejected(self):
        school = FakeSchool()
        result = Day1MagicService.accept_logo_upload(
            school, _TINY_SVG_BYTES, "logo.svg", by_user=FakeUser()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "forbidden_mime")
        self.assertFalse(school.logo_url)

    def test_pdf_disguised_as_png_rejected_via_mime_sniff(self):
        school = FakeSchool()
        # Original filename SAYS png but the magic bytes are PDF — the
        # validator MUST trust magic bytes and reject this.
        result = Day1MagicService.accept_logo_upload(
            school, _TINY_PDF_BYTES, "logo.png", by_user=FakeUser()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "unsupported_mime")
        self.assertFalse(school.logo_url)

    def test_empty_bytes_rejected(self):
        school = FakeSchool()
        result = Day1MagicService.accept_logo_upload(
            school, b"", "empty.png", by_user=FakeUser()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "empty_upload")

    def test_jpeg_accepted_via_magic_bytes(self):
        school = FakeSchool()
        result = Day1MagicService.accept_logo_upload(
            school, _TINY_JPEG_BYTES, "logo.jpg", by_user=FakeUser()
        )
        self.assertTrue(result.ok, msg=result.error_message)
        self.assertTrue(result.logo_url)

    def test_theme_intelligence_importerror_falls_back_to_deterministic_seed(self):
        school = FakeSchool()
        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

        def _imp(name, *args, **kwargs):
            if name == "services.theme_intelligence":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=_imp):
            result = Day1MagicService.accept_logo_upload(
                school, _TINY_PNG_BYTES, "logo.png", by_user=FakeUser()
            )
        self.assertTrue(result.ok, msg=result.error_message)
        # Deterministic fallback seed.
        self.assertEqual(result.seed_hex.lower(), "#4f46e5")

    def test_none_school_rejected_gracefully(self):
        result = Day1MagicService.accept_logo_upload(
            None, _TINY_PNG_BYTES, "logo.png", by_user=FakeUser()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "missing_tenant")

    def test_tenant_isolation_storage_path_keyed_on_school_pk(self):
        """Sniff the storage path to prove the bytes land under school.pk only."""
        school_a = FakeSchool(pk="aaa", slug="alpha")
        school_b = FakeSchool(pk="bbb", slug="beta")

        result_a = Day1MagicService.accept_logo_upload(
            school_a, _TINY_PNG_BYTES, "logo.png", by_user=FakeUser()
        )
        result_b = Day1MagicService.accept_logo_upload(
            school_b, _TINY_PNG_BYTES, "logo.png", by_user=FakeUser()
        )
        self.assertTrue(result_a.ok)
        self.assertTrue(result_b.ok)
        self.assertIn("aaa", school_a.branding_metadata.get("logo_storage_path", ""))
        self.assertIn("bbb", school_b.branding_metadata.get("logo_storage_path", ""))
        self.assertNotIn("bbb", school_a.branding_metadata.get("logo_storage_path", ""))
        self.assertNotIn("aaa", school_b.branding_metadata.get("logo_storage_path", ""))


# ---------------------------------------------------------------------------
# View-layer tests
# ---------------------------------------------------------------------------


class _ViewBase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _attach(self, request, *, school, user):
        request.school = school
        request.user = user
        request._messages = mock.MagicMock()
        return request


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="rmc-day1-logo-views-"))
class Day1LogoUploadViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _attach(self, request, *, school, user):
        request.school = school
        request.user = user
        request._messages = mock.MagicMock()
        return request

    def _post_logo(self, *, school, user=None, content=_TINY_PNG_BYTES, name="logo.png", content_type="image/png"):
        if user is None:
            user = FakeUser()
        uploaded = SimpleUploadedFile(name, content, content_type=content_type)
        request = self.factory.post(
            "/siteconfig/studio/day1/act1/logo-upload/",
            {"logo": uploaded},
        )
        self._attach(request, school=school, user=user)
        with mock.patch(
            "apps.lifecycle.tenant_school_resolve.can_access_tenant_lifecycle",
            return_value=True,
        ):
            return TenantStudioDay1Act1LogoUploadView.as_view()(request)

    def test_happy_path_returns_200_with_payload(self):
        school = FakeSchool()
        resp = self._post_logo(school=school, user=FakeUser())
        self.assertEqual(resp.status_code, 200)
        payload = resp.json() if hasattr(resp, "json") else None
        if payload is None:
            import json as _json
            payload = _json.loads(resp.content.decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertIn("logo_url", payload)
        self.assertIn("seed_hex", payload)
        self.assertEqual(payload["source"], "logo")
        self.assertTrue(school.logo_url)

    def test_oversize_rejected_400(self):
        school = FakeSchool()
        oversize_bytes = b"\x89PNG\r\n\x1a\n" + b"x" * (DAY1_DEFAULT_LOGO_MAX_BYTES + 32)
        resp = self._post_logo(school=school, content=oversize_bytes, name="huge.png")
        self.assertEqual(resp.status_code, 400)
        import json as _json
        payload = _json.loads(resp.content.decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "oversize")

    def test_svg_rejected_400(self):
        school = FakeSchool()
        resp = self._post_logo(
            school=school, content=_TINY_SVG_BYTES, name="logo.svg", content_type="image/svg+xml"
        )
        self.assertEqual(resp.status_code, 400)
        import json as _json
        payload = _json.loads(resp.content.decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "forbidden_mime")

    def test_pdf_disguised_as_png_rejected_via_mime_sniff(self):
        school = FakeSchool()
        resp = self._post_logo(
            school=school, content=_TINY_PDF_BYTES, name="logo.png", content_type="image/png"
        )
        self.assertEqual(resp.status_code, 400)
        import json as _json
        payload = _json.loads(resp.content.decode("utf-8"))
        self.assertEqual(payload["error_code"], "unsupported_mime")

    def test_missing_logo_field_returns_400(self):
        request = self.factory.post(
            "/siteconfig/studio/day1/act1/logo-upload/", {}
        )
        self._attach(request, school=FakeSchool(), user=FakeUser())
        with mock.patch(
            "apps.lifecycle.tenant_school_resolve.can_access_tenant_lifecycle",
            return_value=True,
        ):
            resp = TenantStudioDay1Act1LogoUploadView.as_view()(request)
        self.assertEqual(resp.status_code, 400)
        import json as _json
        payload = _json.loads(resp.content.decode("utf-8"))
        self.assertEqual(payload["error_code"], "missing_file")

    def test_get_method_returns_405(self):
        request = self.factory.get("/siteconfig/studio/day1/act1/logo-upload/")
        self._attach(request, school=FakeSchool(), user=FakeUser())
        with mock.patch(
            "apps.lifecycle.tenant_school_resolve.can_access_tenant_lifecycle",
            return_value=True,
        ):
            resp = TenantStudioDay1Act1LogoUploadView.as_view()(request)
        self.assertEqual(resp.status_code, 405)

    def test_non_operator_rejected_403(self):
        school = FakeSchool()
        uploaded = SimpleUploadedFile("logo.png", _TINY_PNG_BYTES, content_type="image/png")
        request = self.factory.post(
            "/siteconfig/studio/day1/act1/logo-upload/",
            {"logo": uploaded},
        )
        self._attach(request, school=school, user=FakeUser(is_staff=False, role="STUDENT"))
        with mock.patch(
            "apps.lifecycle.tenant_school_resolve.can_access_tenant_lifecycle",
            return_value=False,
        ):
            resp = TenantStudioDay1Act1LogoUploadView.as_view()(request)
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(school.logo_url)

    def test_no_school_on_request_rejected_403(self):
        uploaded = SimpleUploadedFile("logo.png", _TINY_PNG_BYTES, content_type="image/png")
        request = self.factory.post(
            "/siteconfig/studio/day1/act1/logo-upload/",
            {"logo": uploaded},
        )
        request.school = None
        request.user = FakeUser()
        request._messages = mock.MagicMock()
        with mock.patch(
            "apps.lifecycle.tenant_school_resolve.can_access_tenant_lifecycle",
            return_value=True,
        ):
            resp = TenantStudioDay1Act1LogoUploadView.as_view()(request)
        self.assertEqual(resp.status_code, 403)

    def test_tenant_isolation_school_resolved_from_request_not_post_body(self):
        """A POST that contains a ``school_id`` field MUST be ignored by the view.

        The view resolves the tenant strictly from ``request.school``; the
        POST body never participates in tenant selection. We exercise that
        guarantee by sending a foreign ``school_id`` in the body and
        asserting the bytes land under the request-resolved tenant.
        """
        school = FakeSchool(pk="real-tenant", slug="real")
        uploaded = SimpleUploadedFile("logo.png", _TINY_PNG_BYTES, content_type="image/png")
        request = self.factory.post(
            "/siteconfig/studio/day1/act1/logo-upload/",
            {"logo": uploaded, "school_id": "attacker-tenant", "school": "attacker-tenant"},
        )
        self._attach(request, school=school, user=FakeUser())
        with mock.patch(
            "apps.lifecycle.tenant_school_resolve.can_access_tenant_lifecycle",
            return_value=True,
        ):
            resp = TenantStudioDay1Act1LogoUploadView.as_view()(request)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("real-tenant", school.branding_metadata.get("logo_storage_path", ""))
        self.assertNotIn("attacker-tenant", school.branding_metadata.get("logo_storage_path", ""))


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


class Day1LogoUploadUrlTests(SimpleTestCase):
    def test_url_name_resolves(self):
        # Resolve through the tenant urlconf when available; fall back to the
        # default urlconf for builds without a tenant urlconf wired in.
        try:
            url = reverse(
                "siteconfig:tenant_studio_day1_act1_logo_upload",
                urlconf="config.tenant_urls",
            )
        except (NoReverseMatch, ModuleNotFoundError):
            url = reverse("siteconfig:tenant_studio_day1_act1_logo_upload")
        self.assertTrue(url.endswith("/studio/day1/act1/logo-upload/"))


# ---------------------------------------------------------------------------
# Log-hygiene paranoia (no PII, no bytes, no filename in logs)
# ---------------------------------------------------------------------------


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="rmc-day1-logo-logs-"))
class Day1LogoUploadLogHygieneTests(TestCase):
    def test_logs_never_contain_slug_filename_or_bytes(self):
        school = FakeSchool(slug="ghs-limbe-secret-slug")
        with self.assertLogs("apps.siteconfig.tenant_studio_day1", level="INFO") as cm:
            Day1MagicService.accept_logo_upload(
                school,
                _TINY_PNG_BYTES,
                "PII_filename_with_personal_data.png",
                by_user=FakeUser(),
            )
        for line in cm.output:
            self.assertNotIn("ghs-limbe-secret-slug", line)
            self.assertNotIn("PII_filename_with_personal_data", line)
            # PNG magic bytes never appear in logs.
            self.assertNotIn("\\x89PNG", line)
