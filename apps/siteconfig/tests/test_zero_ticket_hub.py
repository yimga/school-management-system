"""Zero-Ticket Hub — diagnostics, contrast remediate, permission simulator."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.siteconfig.contrast_guard import remediate_brand_hex_on_background
from apps.siteconfig.permission_matrix_simulator import simulate_role_capabilities
from apps.siteconfig.tenant_diagnostics import compute_adoption_dimension


class ContrastRemediateTests(TestCase):
    def test_remediate_shifts_low_contrast_brand(self):
        result = remediate_brand_hex_on_background("#ffff00", "#ffffff", min_ratio=7.0)
        self.assertTrue(result["adjusted"] or result["ok"])
        self.assertGreaterEqual(result["remediated_ratio"], result["original_ratio"])

    def test_passing_brand_unchanged(self):
        result = remediate_brand_hex_on_background("#0f172a", "#ffffff", min_ratio=4.5)
        self.assertFalse(result["adjusted"])
        self.assertTrue(result["ok"])


class AdoptionDimensionTests(TestCase):
    def test_adoption_zero_without_school(self):
        self.assertEqual(compute_adoption_dimension(None), 0)


class PermissionSimulatorTests(TestCase):
    def test_teacher_cannot_admin_settings(self):
        simulation = simulate_role_capabilities(school=None, role="TEACHER")
        admin_cap = next(
            c for c in simulation["capabilities"] if c["key"] == "manage_settings"
        )
        self.assertFalse(admin_cap["visible"])


class ZeroTicketHubViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="zt_admin",
            password="Test1234",
            email="zt_admin@example.com",
        )
        self.client = Client()

    def test_api_diagnostics_requires_auth(self):
        url = reverse("siteconfig:api_tenant_diagnostics")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (302, 403))

    def test_api_brand_remediate_json(self):
        self.client.force_login(self.user)
        url = reverse("siteconfig:api_brand_contrast_remediate")
        resp = self.client.post(
            url,
            data='{"brand_hex":"#ffff00","background_hex":"#ffffff","min_ratio":7}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("remediated_hex", body)


class PermissionMatrixExportTests(TestCase):
    def setUp(self):
        import uuid

        from apps.schools.models import School

        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="zt_export",
            password="Test1234",
            email="zt_export@example.com",
        )
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Perm {uid}",
            slug=f"perm-{uid}",
            subdomain=f"perm{uid}",
            is_active=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_role_divergence_admin_vs_parent(self):
        from apps.siteconfig.permission_matrix_simulator import (
            simulate_role_capabilities,
        )

        admin = simulate_role_capabilities(school=None, role="ADMIN")
        parent = simulate_role_capabilities(school=None, role="PARENT")
        self.assertGreater(admin["role_rank"], parent["role_rank"])

    def test_export_json_endpoint(self):
        url = reverse("siteconfig:api_permission_matrix_export")
        resp = self.client.get(url + "?role=TEACHER&format=json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("capabilities", resp.json())
