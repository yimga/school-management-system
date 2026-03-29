"""Runtime truth hub: super-only read-only RuntimeDefaults + slim SiteSettings summary."""

import hashlib

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorTruthHubLink
from apps.runtime_blueprints.models import BlueprintPack
from apps.schools.decision_architecture import (
    DECISION_ARCHITECTURE_KEYS,
    get_decision_architecture_for_page,
)


@override_settings(ALLOWED_HOSTS=["*"])
class RuntimeTruthHubTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="truth_hub_tester",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.host = "manager.runmycampus.com"
        cache.clear()

    def test_runtime_truth_hub_renders_200(self):
        url = reverse("super:runtime_truth_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Runtime truth hub", html=False)
        self.assertContains(response, "Migration playbooks", html=False)
        self.assertContains(response, "automation.playbook.execute", html=False)
        self.assertContains(response, "/admin/automation/migrationplaybook/", html=False)
        slugs = tuple(
            BlueprintPack.objects.order_by("slug").values_list("slug", flat=True)
        )
        body = "\n".join(slugs).encode("utf-8")
        digest = hashlib.sha256(body).hexdigest()[:16]
        fingerprint = f"n={len(slugs)};sha256[:16]={digest}"
        self.assertContains(response, fingerprint, html=False)

    def test_runtime_truth_hub_phase_h_skip_link_targets_main(self):
        url = reverse("super:runtime_truth_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#runtime-truth-hub-main"', body)
        self.assertIn('id="runtime-truth-hub-main"', body)

    def test_runtime_truth_hub_renders_operator_truth_hub_links(self):
        PlatformOperatorTruthHubLink.objects.create(
            slug="phase-b-diff",
            label="Phase B diff (test)",
            href="/super/phase-b-snapshot-diff/",
            sort_order=0,
        )
        url = reverse("super:runtime_truth_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operator curated links", html=False)
        self.assertContains(response, "Phase B diff (test)", html=False)

    def test_runtime_truth_hub_passes_decision_architecture_context(self):
        """View uses render() (plain HttpResponse); assert preset via template attrs."""
        url = reverse("super:runtime_truth_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        expected = get_decision_architecture_for_page("runtime_truth_hub")
        self.assertEqual(set(expected.keys()), set(DECISION_ARCHITECTURE_KEYS))
        for key in DECISION_ARCHITECTURE_KEYS:
            val = expected[key]
            self.assertTrue(str(val).strip(), msg=f"empty preset {key!r}")
            self.assertContains(response, val, html=False)
