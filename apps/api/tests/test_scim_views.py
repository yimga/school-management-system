import hashlib
import hmac
import json
import time

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AccessRole, User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import ServiceIntegration


class ScimViewsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="SCIM School",
            slug="scim-school",
            subdomain="scim-school",
            is_active=True,
        )
        self.integration = ServiceIntegration.objects.create(
            school=self.school,
            service_name="SCIM Directory",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            client_secret="token-abc",
            config={"bearer_token": "token-abc", "default_role": "TEACHER"},
            is_active=True,
        )
        self.other_school = School.objects.create(
            name="SCIM Other School",
            slug="scim-other-school",
            subdomain="scim-other-school",
            is_active=True,
        )
        self.other_integration = ServiceIntegration.objects.create(
            school=self.other_school,
            service_name="SCIM Directory Other",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            client_secret="token-other",
            config={"bearer_token": "token-other", "default_role": "TEACHER"},
            is_active=True,
        )
        self.base_user = User.objects.create_user(
            username="base.user",
            email="base@example.com",
            password="x",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            school=self.school,
            user=self.base_user,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        self.role = AccessRole.objects.create(code="scim_teacher", name="SCIM Teacher")

    def _headers(self, token: str = "token-abc"):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _url(self, name: str, *args):
        base = reverse(name, args=args)
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}school_slug={self.school.slug}"

    def test_service_provider_config_requires_token(self):
        response = self.client.get(self._url("api:scim-service-provider-config"))
        self.assertEqual(response.status_code, 403)

    def test_scim_rejects_timestamp_outside_replay_window(self):
        stale_ts = int(time.time()) - 400  # > 5 min default window
        response = self.client.get(
            self._url("api:scim-users"),
            **self._headers(),
            HTTP_X_SCIM_TIMESTAMP=str(stale_ts),
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("window", response.json()["detail"].lower())

    def test_scim_accepts_timestamp_within_replay_window(self):
        fresh_ts = int(time.time())
        response = self.client.get(
            self._url("api:scim-users"),
            **self._headers(),
            HTTP_X_SCIM_TIMESTAMP=str(fresh_ts),
        )
        self.assertEqual(response.status_code, 200)

    def test_scim_rejects_invalid_timestamp_header(self):
        response = self.client.get(
            self._url("api:scim-users"),
            **self._headers(),
            HTTP_X_SCIM_TIMESTAMP="not-an-int",
        )
        self.assertEqual(response.status_code, 401)

    def _hmac_sha256_hex(self, secret: str, body: bytes) -> str:
        return hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()

    def test_scim_accepts_valid_hmac_signature_on_get(self):
        body = b""
        sig = self._hmac_sha256_hex("token-abc", body)
        response = self.client.get(
            self._url("api:scim-users"),
            **self._headers(),
            HTTP_X_SCIM_SIGNATURE=f"sha256={sig}",
        )
        self.assertEqual(response.status_code, 200)

    def test_scim_rejects_invalid_hmac_signature(self):
        response = self.client.get(
            self._url("api:scim-users"),
            **self._headers(),
            HTTP_X_SCIM_SIGNATURE="sha256=" + "a" * 64,
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("signature", response.json()["detail"].lower())

    def test_scim_rejects_malformed_signature_prefix(self):
        response = self.client.get(
            self._url("api:scim-users"),
            **self._headers(),
            HTTP_X_SCIM_SIGNATURE="md5=deadbeef",
        )
        self.assertEqual(response.status_code, 401)

    def test_scim_rejects_signature_digest_not_64_hex_chars(self):
        response = self.client.get(
            self._url("api:scim-users"),
            **self._headers(),
            HTTP_X_SCIM_SIGNATURE="sha256=" + "a" * 63,
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("length", response.json()["detail"].lower())

    def test_scim_accepts_valid_hmac_signature_on_post_body(self):
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "hmac.user",
            "name": {"givenName": "H", "familyName": "Mac"},
            "emails": [{"value": "hmac@example.com", "primary": True}],
            "active": True,
        }
        raw = json.dumps(payload).encode("utf-8")
        sig = self._hmac_sha256_hex("token-abc", raw)
        response = self.client.post(
            self._url("api:scim-users"),
            data=raw,
            content_type="application/json",
            **self._headers(),
            HTTP_X_SCIM_SIGNATURE=f"sha256={sig}",
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_scim_duplicate_nonce_rejected_on_second_request(self):
        cache.clear()
        nonce = "unique-nonce-phase-ii-1"
        headers = {**self._headers(), "HTTP_X_SCIM_NONCE": nonce}
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "nonce.user.one",
            "name": {"givenName": "N", "familyName": "One"},
            "emails": [{"value": "n1@example.com", "primary": True}],
            "active": True,
        }
        r1 = self.client.post(
            self._url("api:scim-users"),
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(r1.status_code, 201, r1.content)
        r2 = self.client.post(
            self._url("api:scim-users"),
            data=json.dumps(
                {
                    **payload,
                    "userName": "nonce.user.two",
                    "emails": [{"value": "n2@example.com", "primary": True}],
                }
            ),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(r2.status_code, 401)
        self.assertIn("nonce", r2.json()["detail"].lower())

    def test_scim_nonce_not_consumed_when_unauthorized(self):
        cache.clear()
        nonce = "nonce-unauth-should-not-burn"
        bad = self.client.get(
            self._url("api:scim-users"),
            **self._headers(token="wrong-token"),
            HTTP_X_SCIM_NONCE=nonce,
        )
        self.assertEqual(bad.status_code, 403)
        good = self.client.get(
            self._url("api:scim-users"),
            **self._headers(),
            HTTP_X_SCIM_NONCE=nonce,
        )
        self.assertEqual(good.status_code, 200)

    def test_create_user_via_scim(self):
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "teacher.scim",
            "name": {"givenName": "Teacher", "familyName": "Scim"},
            "emails": [{"value": "teacher.scim@example.com", "primary": True}],
            "active": True,
        }
        response = self.client.post(
            self._url("api:scim-users"),
            data=json.dumps(payload),
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["userName"], "teacher.scim")
        user = User.objects.get(username="teacher.scim")
        self.assertTrue(
            SchoolMembership.objects.filter(school=self.school, user=user).exists()
        )

    def test_create_user_rejects_invalid_json(self):
        response = self.client.post(
            self._url("api:scim-users"),
            data="{bad-json",
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["scimType"], "invalidSyntax")

    def test_create_user_rejects_non_scim_content_type(self):
        response = self.client.post(
            self._url("api:scim-users"),
            data=json.dumps({"userName": "teacher.scim"}),
            content_type="text/plain",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("application/scim+json", response.json()["detail"])

    def test_create_user_rejects_non_object_json_body(self):
        response = self.client.post(
            self._url("api:scim-users"),
            data=json.dumps(["not", "an", "object"]),
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["scimType"], "invalidSyntax")

    def test_create_user_requires_user_schema(self):
        response = self.client.post(
            self._url("api:scim-users"),
            data=json.dumps({"userName": "teacher.scim"}),
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["scimType"], "invalidSyntax")
        self.assertIn("core User schema", response.json()["detail"])

    def test_list_users_supports_filter(self):
        response = self.client.get(
            self._url("api:scim-users") + '&filter=userName eq "base.user"',
            **self._headers(),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            data["schemas"][0], "urn:ietf:params:scim:api:messages:2.0:ListResponse"
        )
        self.assertEqual(data["totalResults"], 1)
        self.assertEqual(data["Resources"][0]["userName"], "base.user")

    def test_list_users_pagination_reports_filtered_total_results(self):
        for idx in range(3):
            user = User.objects.create_user(
                username=f"extra.user.{idx}",
                email=f"extra{idx}@example.com",
                password="x",
                role=User.Role.TEACHER,
            )
            SchoolMembership.objects.create(
                school=self.school,
                user=user,
                role=User.Role.TEACHER,
                is_primary=False,
            )
        response = self.client.get(
            self._url("api:scim-users") + "&startIndex=2&count=2",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["startIndex"], 2)
        self.assertEqual(data["itemsPerPage"], 2)
        self.assertEqual(data["totalResults"], 4)
        self.assertEqual(len(data["Resources"]), 2)

    def test_list_users_accepts_count_zero_for_metadata_only(self):
        response = self.client.get(
            self._url("api:scim-users") + "&count=0",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["itemsPerPage"], 0)
        self.assertGreaterEqual(data["totalResults"], 1)
        self.assertEqual(data["Resources"], [])

    def test_scim_rejects_cross_tenant_token_usage(self):
        url = reverse("api:scim-users") + f"?school_slug={self.other_school.slug}"
        response = self.client.get(url, **self._headers(token="token-abc"))
        self.assertEqual(response.status_code, 403)

    def test_patch_user_deactivate(self):
        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        }
        response = self.client.patch(
            self._url("api:scim-user-detail", self.base_user.pk),
            data=json.dumps(payload),
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.base_user.refresh_from_db()
        self.assertFalse(self.base_user.is_active)

    def test_patch_user_rejects_invalid_json(self):
        response = self.client.patch(
            self._url("api:scim-user-detail", self.base_user.pk),
            data="{bad-json",
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["scimType"], "invalidSyntax")

    def test_patch_group_rejects_non_scim_content_type(self):
        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "add",
                    "path": "members",
                    "value": [{"value": str(self.base_user.pk)}],
                }
            ],
        }
        response = self.client.patch(
            self._url("api:scim-group-detail", self.role.pk),
            data=json.dumps(payload),
            content_type="text/plain",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 415)
        self.assertIn("application/scim+json", response.json()["detail"])

    def test_delete_user_deprovisions(self):
        response = self.client.delete(
            self._url("api:scim-user-detail", self.base_user.pk),
            **self._headers(),
        )
        self.assertEqual(response.status_code, 204)
        self.base_user.refresh_from_db()
        self.assertFalse(self.base_user.is_active)

    def test_group_patch_adds_role_to_user(self):
        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "add",
                    "path": "members",
                    "value": [{"value": str(self.base_user.pk)}],
                }
            ],
        }
        response = self.client.patch(
            self._url("api:scim-group-detail", self.role.pk),
            data=json.dumps(payload),
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.base_user.roles.filter(pk=self.role.pk).exists())

    def test_scim_groups_post_creates_access_role(self):
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "IdP Group Alpha",
        }
        response = self.client.post(
            self._url("api:scim-groups"),
            data=json.dumps(payload),
            content_type="application/json",
            **self._headers(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data.get("displayName"), "IdP Group Alpha")
        self.assertTrue(AccessRole.objects.filter(name="IdP Group Alpha").exists())

    def test_scim_endpoints_rate_limit_429_when_exceeded(self):
        from unittest.mock import patch

        urls = [
            self._url("api:scim-service-provider-config"),
            self._url("api:scim-users"),
            self._url("api:scim-user-detail", self.base_user.pk),
            self._url("api:scim-groups"),
            self._url("api:scim-group-detail", self.role.pk),
        ]
        with patch("apps.api.scim_views.throttle_ip_request", return_value=(False, 45)):
            for url in urls:
                response = self.client.get(url, **self._headers())
                self.assertEqual(response.status_code, 429, msg=url)
                self.assertEqual(response["Retry-After"], "45", msg=url)
