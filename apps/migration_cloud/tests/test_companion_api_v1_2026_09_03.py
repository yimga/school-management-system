"""Companion /api/v1/ JWT surface (2026-09-03).

Proves the seven paths the Tauri + Docker siblings hardcode resolve and
that login + receipt fetch behave with Bearer auth.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse
from rest_framework_simplejwt.tokens import RefreshToken

from apps.migration_cloud.models import (
    BundleStatus,
    CompanionUploadReceipt,
    MigrationAuthorizationAgreement,
    MigrationBundle,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class CompanionApiV1UrlResolutionTests(SimpleTestCase):
    _PATHS = (
        "/api/v1/auth/login/",
        "/api/v1/migration/maa/text/",
        "/api/v1/migration/maa/sign/",
        "/api/v1/migration/companion/upload/",
        "/api/v1/migration/companion/server-pubkey/",
        "/api/v1/migration/receipts/",
        "/api/v1/migration/receipts/42/",
    )

    @override_settings(ROOT_URLCONF="config.urls")
    def test_companion_paths_resolve_on_default_urlconf(self):
        for path in self._PATHS:
            match = resolve(path)
            self.assertIsNotNone(match.func, msg=path)

    def test_named_routes_exist(self):
        reverse("api_v1:companion-auth-login")
        reverse("api_v1:companion-maa-text")
        reverse("api_v1:companion-receipt-detail", kwargs={"receipt_id": 1})


@override_settings(ROOT_URLCONF="config.urls")
class CompanionApiV1LoginTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Companion API School",
            slug="companion-api-school",
            subdomain="companion-api-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="companion-op",
            email="companion-op@example.com",
            password="Comp@nionPass1",
            role="ADMIN",
        )
        SchoolMembership.objects.create(user=self.user, school=self.school)

    def test_login_returns_bearer_token(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps(
                {"email": "companion-op@example.com", "password": "Comp@nionPass1"}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        token = body.get("token") or body.get("access")
        self.assertTrue(token)

    def test_login_rejects_bad_password(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps(
                {"email": "companion-op@example.com", "password": "wrong"}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)


@override_settings(ROOT_URLCONF="config.urls")
class CompanionApiV1ReceiptTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Receipt School",
            slug="receipt-school",
            subdomain="receipt-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="receipt-op",
            email="receipt-op@example.com",
            password="ReceiptPass1",
            role="ADMIN",
        )
        SchoolMembership.objects.create(user=self.user, school=self.school)
        refresh = RefreshToken.for_user(self.user)
        self.auth_header = f"Bearer {refresh.access_token}"

        self.maa = MigrationAuthorizationAgreement.objects.create(
            tenant=self.school,
            signed_by_user=self.user,
            signed_by_role="ADMIN",
            vendor_source="powerschool",
            vendor_account_holder_name="Test Holder",
            agreement_version="v1.0",
            signature_text="signed",
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            schema_name="receipt_school",
            label="test",
            status=BundleStatus.PENDING,
            triggered_by=self.user,
        )
        from apps.migration_cloud.models import CompanionCiphertextBlob

        self.blob = CompanionCiphertextBlob.objects.create(
            tenant=self.school,
            ciphertext_sha256="a" * 64,
            byte_size=10,
        )
        self.receipt = CompanionUploadReceipt.objects.create(
            tenant=self.school,
            bundle=self.bundle,
            maa=self.maa,
            ciphertext_blob=self.blob,
            client_idempotency_key="idem-companion-api-test",
            ciphertext_sha256="a" * 64,
        )

    def test_receipt_detail_requires_auth(self):
        response = self.client.get(f"/api/v1/migration/receipts/{self.receipt.pk}/")
        self.assertEqual(response.status_code, 401)

    def test_receipt_detail_returns_payload(self):
        response = self.client.get(
            f"/api/v1/migration/receipts/{self.receipt.pk}/",
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["receipt_id"], self.receipt.pk)
        self.assertEqual(body["bundle_id"], self.bundle.pk)
        self.assertEqual(body["status"], BundleStatus.PENDING)

    def test_receipt_list_scoped_to_membership(self):
        response = self.client.get(
            "/api/v1/migration/receipts/",
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        ids = [row["receipt_id"] for row in response.json().get("receipts", [])]
        self.assertIn(self.receipt.pk, ids)

    def test_maa_text_requires_tenant_query(self):
        response = self.client.get(
            "/api/v1/migration/maa/text/?vendor=powerschool",
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body.get("code"), "missing_tenant")

    def test_maa_text_with_tenant_query(self):
        response = self.client.get(
            "/api/v1/migration/maa/text/?vendor=powerschool&tenant=receipt-school",
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertIn("text", body)
