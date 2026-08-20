"""Deliverable C — media/branding portability (cloud → offline edge box).

Proves a school's logo + colours + brand profile survive a move to an offline box:
  * round-trip export→import applies branding to a DIFFERENT (box-side) school;
  * the logo is offline-safe — it renders with NO media server via a DB-resident
    data URI, synthesized from the source file when only a file exists;
  * import writes the logo into the box MEDIA_ROOT and sets a box-relative /media/…
    logo_url (never the old non-resolving .school.lan URL);
  * the envelope is fail-closed (tampered signature is rejected);
  * runbook step 4 now prescribes the export/import pair and validates that the logo
    actually resolves offline (not just a non-empty URL).
"""
from __future__ import annotations

import base64
import json

from django.core.files.storage import default_storage
from django.test import TestCase

from apps.lifecycle.branding_portability import (
    export_school_branding,
    import_school_branding,
)
from apps.platform_runtime.storage import (
    get_storage_url,
    save_to_storage,
    tenant_media_path,
)
from apps.schools.models import School

# A tiny but valid-enough PNG header; content is opaque to the round-trip.
_LOGO = b"\x89PNG\r\n\x1a\n" + b"gilead-logo-bytes" * 4
_LOGO_DATA_URI = "data:image/png;base64," + base64.b64encode(_LOGO).decode("ascii")


class _Base(TestCase):
    def setUp(self):
        self._written: list[str] = []

    def tearDown(self):
        for path in self._written:
            try:
                default_storage.delete(path)
            except Exception:  # noqa: BLE001
                pass

    def _school(self, slug, **extra):
        return School.objects.create(
            name=f"School {slug}", slug=slug, subdomain=slug,
            is_active=True, is_approved=True, country_code="CM", settings={}, **extra,
        )


class BrandingRoundTripTests(_Base):
    def test_data_uri_logo_round_trips_to_a_box_school(self):
        cloud = self._school(
            "cloud-brand",
            primary_color="#123456", accent_color="#abcdef",
            branding_metadata={"logo_data_uri": _LOGO_DATA_URI, "primary": "#123456"},
        )
        blob = export_school_branding(cloud)

        box = self._school("box-brand")  # fresh, no branding
        res = import_school_branding(blob, school=box, write_media=False)

        box.refresh_from_db()
        self.assertTrue(res["logo_offline_ok"])
        self.assertEqual(box.branding_metadata.get("logo_data_uri"), _LOGO_DATA_URI)
        self.assertEqual(box.primary_color, "#123456")
        self.assertEqual(box.accent_color, "#abcdef")

    def test_file_only_logo_becomes_offline_safe_data_uri(self):
        cloud = self._school("cloud-file")
        rel = save_to_storage(tenant_media_path(cloud.pk, "brand/logo.png"), _LOGO, "image/png")
        self._written.append(rel)
        cloud.logo_url = get_storage_url(rel)  # /media/tenants/{pk}/brand/logo.png
        cloud.branding_metadata = {"logo_storage_path": rel}
        cloud.save(update_fields=["logo_url", "branding_metadata"])

        blob = export_school_branding(cloud)
        box = self._school("box-file")
        res = import_school_branding(blob, school=box, write_media=False)

        box.refresh_from_db()
        # The file was inlined at export, so the box renders it with no media server.
        self.assertTrue(res["logo_offline_ok"])
        self.assertTrue(box.branding_metadata.get("logo_data_uri", "").startswith("data:image/png;base64,"))

    def test_media_write_sets_box_relative_url_not_school_lan(self):
        cloud = self._school(
            "cloud-media",
            branding_metadata={"logo_data_uri": _LOGO_DATA_URI},
        )
        blob = export_school_branding(cloud)
        box = self._school("box-media")

        res = import_school_branding(blob, school=box, write_media=True)
        self._written.extend(res["media_written"])

        box.refresh_from_db()
        self.assertTrue(res["media_written"])            # a file was written on the box
        self.assertNotIn(".school.lan", box.logo_url)    # not the old non-resolving URL
        self.assertIn("/media/", box.logo_url)           # box-resolvable relative path
        self.assertIn(str(box.pk), box.logo_url)         # under the box school's media dir

    def test_brand_profile_is_carried(self):
        from apps.brand_experience.models import BrandProfile

        cloud = self._school("cloud-bp", branding_metadata={"logo_data_uri": _LOGO_DATA_URI})
        BrandProfile.objects.update_or_create(
            school=cloud,
            defaults={"primary_color": "#ff0000", "tagline": "Excellence", "font_family": "Inter"},
        )
        blob = export_school_branding(cloud)

        box = self._school("box-bp")
        res = import_school_branding(blob, school=box, write_media=False)

        self.assertTrue(res["brand_profile_restored"])
        bp = BrandProfile.objects.get(school=box)
        self.assertEqual(bp.tagline, "Excellence")
        self.assertEqual(bp.primary_color, "#ff0000")


class BrandingFailClosedTests(_Base):
    def test_tampered_signature_is_rejected(self):
        cloud = self._school("cloud-tamper", branding_metadata={"logo_data_uri": _LOGO_DATA_URI})
        blob = export_school_branding(cloud)
        container = json.loads(blob)
        container["sig"] = "deadbeef" * 8  # forge
        tampered = json.dumps(container).encode("utf-8")

        box = self._school("box-tamper")
        with self.assertRaises(ValueError):
            import_school_branding(tampered, school=box)

    def test_wrong_format_is_rejected(self):
        box = self._school("box-wrongfmt")
        with self.assertRaises(ValueError):
            import_school_branding(json.dumps({"format": "nope"}).encode("utf-8"), school=box)


class MediaBrandingValidationTests(_Base):
    def test_data_uri_passes(self):
        from apps.lifecycle.edge_onboarding import _validate_media_branding

        s = self._school("val-datauri", branding_metadata={"logo_data_uri": _LOGO_DATA_URI})
        ok, msg = _validate_media_branding(s)
        self.assertTrue(ok, msg)
        self.assertIn("offline", msg.lower())

    def test_off_box_https_url_only_fails(self):
        from apps.lifecycle.edge_onboarding import _validate_media_branding

        s = self._school(
            "val-https",
            logo_url="https://val-https.school.lan/media/tenants/1/logo.png",
            branding_metadata={},
        )
        ok, msg = _validate_media_branding(s)
        self.assertFalse(ok)
        self.assertIn("offline", msg.lower())


class RunbookStep4Tests(_Base):
    def test_media_step_prescribes_the_command_pair(self):
        from apps.lifecycle.edge_onboarding import generate_runbook

        school = self._school("gilead-tech")
        rb = generate_runbook(school)
        media = next(s for s in rb["steps"] if s["key"] == "media_branding")
        export = next(s for s in rb["steps"] if s["key"] == "export_cloud_artifacts")

        self.assertIn("import_school_branding", media["command"])
        self.assertIn("export_school_branding", export["command"])
        self.assertNotIn(".school.lan", media["command"])
        self.assertIn(school.slug, media["command"])
