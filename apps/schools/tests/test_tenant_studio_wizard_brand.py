"""Tenant Studio create-school wizard: logo upload + guidance."""

from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from unittest.mock import patch

from apps.accounts.models import User
from apps.brand_experience.models import BrandProfile
from apps.schools.models import School
from apps.schools.school_brand_assets import (
    persist_school_brand_favicon,
    persist_school_brand_logo,
)
from apps.schools.tenant_studio_guidance import wizard_context


@override_settings(MEDIA_ROOT="/tmp/rmc-test-media")
class TenantStudioWizardBrandTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="cp_admin_studio",
            email="cp@example.com",
            password="Test1234!",
        )

    def test_wizard_context_serializes_guidance(self):
        ctx = wizard_context()
        self.assertEqual(len(ctx["wizard_steps_meta"]), 4)
        parsed = json.loads(ctx["wizard_steps_json"])
        self.assertTrue(parsed[0].get("tip"))
        self.assertIn("name", ctx["wizard_field_tags"])

    def test_persist_school_brand_logo_sets_urls(self):
        school = School.objects.create(
            name="Logo Test School",
            slug="logo-test-school",
            subdomain="logo-test-school",
        )
        upload = SimpleUploadedFile(
            "logo.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png",
        )
        url = persist_school_brand_logo(school=school, uploaded_file=upload)
        school.refresh_from_db()
        self.assertTrue(url)
        self.assertEqual(school.logo_url, url)
        profile = BrandProfile.objects.get(school=school)
        self.assertEqual(profile.logo_url, url)
        self.assertTrue((school.settings or {}).get("provisioning", {}).get("logo_uploaded"))

    def test_persist_school_brand_favicon_sets_profile_url(self):
        school = School.objects.create(
            name="Favicon School",
            slug="favicon-school",
            subdomain="favicon-school",
        )
        upload = SimpleUploadedFile(
            "favicon.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png",
        )
        url = persist_school_brand_favicon(school=school, uploaded_file=upload)
        profile = BrandProfile.objects.get(school=school)
        self.assertEqual(profile.favicon_url, url)
        self.assertTrue((school.settings or {}).get("provisioning", {}).get("favicon_uploaded"))

    def test_api_create_school_accepts_multipart_logo(self):
        from apps.schools.super_views_provisioning import api_create_school

        payload = {
            "name": "Multipart School",
            "slug": "multipart-school",
            "subdomain": "multipart-school",
            "contact_email": "admin@multipart.test",
            "country_code": "CM",
            "sub_system": "EN",
        }
        logo = SimpleUploadedFile(
            "brand.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png",
        )
        factory = RequestFactory()
        favicon = SimpleUploadedFile(
            "favicon.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            content_type="image/png",
        )
        request = factory.post(
            "/super/api/create-school/",
            {"payload": json.dumps(payload), "logo": logo, "favicon": favicon},
        )
        request.user = self.superuser
        with patch(
            "apps.schools.tasks.dispatch_provision_school",
            return_value={"job_id": "job-test", "message": "queued"},
        ):
            response = api_create_school(request)
        self.assertEqual(response.status_code, 202)
        school_id = json.loads(response.content.decode()).get("school_id")
        school = School.objects.get(pk=school_id)
        self.assertTrue(school.logo_url)
        profile = BrandProfile.objects.get(school=school)
        self.assertTrue(profile.logo_url)
        self.assertTrue(profile.favicon_url)
        body = json.loads(response.content.decode())
        self.assertIn("tenant_360_url", body)
        self.assertIn("theme_hub_url", body)
        self.assertTrue(body.get("tenant_360_url"))
        self.assertTrue(body.get("theme_hub_url"))

    def test_create_school_wizard_renders_logo_upload(self):
        from apps.schools.super_views_create_school_wizard import create_school_wizard

        factory = RequestFactory()
        request = factory.get("/super/create/")
        request.user = self.superuser
        response = create_school_wizard(request)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="school_logo"', html)
        self.assertIn('id="school_favicon"', html)
        self.assertIn("tenant-studio-wizard", html)
        self.assertIn("rmc-info-tag", html)
        self.assertNotIn("Logo upload can be done after creation", html)
