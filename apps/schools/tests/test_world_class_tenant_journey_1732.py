"""Tests for world-class tenant journey batches 1732–1742."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class SchoolReadinessOfflineFieldsTests(SimpleTestCase):
    def test_readiness_module_has_offline_fields(self):
        text = open("apps/schools/school_readiness.py", encoding="utf-8").read()
        self.assertIn("cached_at", text)
        self.assertIn("offline_hint", text)


class LaunchPlaybookTests(TestCase):
    def test_playbook_hidden_before_launch(self):
        from apps.schools.models import School
        from apps.schools.launch_playbook import build_launch_playbook

        school = School.objects.create(name="Playbook Test", slug="playbook-test-wc")
        payload = build_launch_playbook(school)
        self.assertTrue(payload.get("ok"))
        self.assertFalse(payload.get("visible"))


class DisciplineApiUrlTests(SimpleTestCase):
    def test_api_discipline_incidents_resolves(self):
        name = reverse("api_discipline_incidents", urlconf="config.tenant_urls")
        self.assertIn("discipline", name)
