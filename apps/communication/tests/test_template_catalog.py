"""Tests for the communication template catalog + DB resolver."""

from __future__ import annotations

from django.test import TestCase

from apps.communication.models import CommunicationTemplate
from apps.communication.template_catalog import (
    COMMUNICATION_TEMPLATES,
    get_template,
    is_valid_key,
    list_template_keys,
    resolve_template,
    templates_for_channel,
)
from apps.global_registries.models import RegionConfig
from apps.schools.models import School


class CatalogTests(TestCase):
    def test_catalog_has_canonical_keys(self):
        keys = set(list_template_keys())
        for required in {
            "attendance.absent_today",
            "grades.published",
            "finance.invoice_issued",
            "finance.invoice_overdue",
            "auth.password_reset",
            "emergency.school_closure",
        }:
            self.assertIn(required, keys)

    def test_get_template_unknown_key_returns_none(self):
        self.assertIsNone(get_template("does.not.exist"))

    def test_is_valid_key(self):
        self.assertTrue(is_valid_key("attendance.absent_today"))
        self.assertFalse(is_valid_key("nope"))

    def test_templates_for_channel(self):
        sms = templates_for_channel("sms")
        self.assertGreater(len(sms), 0)
        for key in sms:
            self.assertIn("sms", COMMUNICATION_TEMPLATES[key]["channels"])


class ResolveTemplateTests(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="US",
            defaults={
                "name": "United States",
                "default_language": "en",
                "timezone": "America/New_York",
                "date_format": "MM/DD/YYYY",
                "grading_scale": "0-100",
                "default_currency": "USD",
            },
        )
        self.school_a = School.objects.create(
            name="School A", slug="school-a", subdomain="school-a",
            default_region=self.region, is_active=True,
        )
        self.school_b = School.objects.create(
            name="School B", slug="school-b", subdomain="school-b",
            default_region=self.region, is_active=True,
        )

    def test_falls_back_to_catalog_when_no_override(self):
        out = resolve_template("attendance.absent_today", school=self.school_a)
        self.assertIn("Hi {guardian_first_name}", out["body_template"])
        # No source key means catalog (not "db")
        self.assertNotEqual(out.get("source"), "db")

    def test_tenant_override_wins(self):
        CommunicationTemplate.objects.create(
            school=self.school_a,
            key="attendance.absent_today",
            subject_template="A subject",
            body_template="TENANT_A body",
            is_active=True,
        )
        out_a = resolve_template("attendance.absent_today", school=self.school_a)
        self.assertEqual(out_a["body_template"], "TENANT_A body")
        self.assertEqual(out_a.get("source"), "db")

        out_b = resolve_template("attendance.absent_today", school=self.school_b)
        self.assertIn("Hi {guardian_first_name}", out_b["body_template"])

    def test_platform_override_used_when_no_tenant_override(self):
        CommunicationTemplate.objects.create(
            school=None,
            key="attendance.absent_today",
            body_template="PLATFORM body",
            is_active=True,
        )
        out = resolve_template("attendance.absent_today", school=self.school_a)
        self.assertEqual(out["body_template"], "PLATFORM body")

    def test_inactive_override_ignored(self):
        CommunicationTemplate.objects.create(
            school=self.school_a,
            key="attendance.absent_today",
            body_template="INACTIVE body",
            is_active=False,
        )
        out = resolve_template("attendance.absent_today", school=self.school_a)
        self.assertNotEqual(out["body_template"], "INACTIVE body")

    def test_locale_override_preferred(self):
        CommunicationTemplate.objects.create(
            school=self.school_a, key="attendance.absent_today",
            body_template="EN body", locale="", is_active=True,
        )
        CommunicationTemplate.objects.create(
            school=self.school_a, key="attendance.absent_today",
            body_template="FR body", locale="fr-CM", is_active=True,
        )
        out = resolve_template(
            "attendance.absent_today", school=self.school_a, locale="fr-CM"
        )
        self.assertEqual(out["body_template"], "FR body")

    def test_hard_fallback_for_unknown_key(self):
        out = resolve_template("does.not.exist", school=self.school_a)
        self.assertEqual(out["body_template"], "(template missing)")
        self.assertEqual(out.get("source"), "hard_fallback")
