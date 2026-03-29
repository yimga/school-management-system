"""
Control-plane bridge manifest API — §2.1.1 SOT; automation parity for admin bridges.
"""

import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.super_admin_bridge_registry import (
    PLATFORM_ADMIN_BRIDGE_ORDER,
    PLATFORM_ADMIN_BRIDGES,
)


@override_settings(ALLOWED_HOSTS=["*"])
class ControlPlaneBridgeManifestAPITests(TestCase):
    def test_manifest_auth_and_json_shape(self):
        staff_only = User.objects.create_user(
            username="cp_bridge_manifest_staff",
            password="secret123",
            is_staff=True,
            is_superuser=False,
        )
        superuser = User.objects.create_user(
            username="cp_bridge_manifest_su",
            password="secret123",
            is_staff=True,
            is_superuser=True,
        )
        url = reverse("api:api-control-plane-bridge-manifest")

        self.client.force_login(staff_only)
        r403 = self.client.get(url)
        self.assertEqual(r403.status_code, 403)

        self.client.force_login(superuser)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content[:500])
        data = json.loads(r.content)
        self.assertIn("bridges", data)
        self.assertIn("bridge_count", data)
        self.assertGreater(data["bridge_count"], 10)
        bridges = data["bridges"]
        self.assertEqual(
            len(bridges),
            data["bridge_count"],
            msg="bridge_count must match bridges[] length (batch 17 #178 / batch 18 #193)",
        )
        expected_keys = [
            k
            for k in PLATFORM_ADMIN_BRIDGE_ORDER
            if PLATFORM_ADMIN_BRIDGES.get(k) and PLATFORM_ADMIN_BRIDGES[k].get("admin_url")
        ]
        self.assertEqual(
            [b.get("bridge_key") for b in bridges],
            expected_keys,
            msg="API manifest order must follow PLATFORM_ADMIN_BRIDGE_ORDER with admin_url",
        )
        keys = {b.get("bridge_key") for b in bridges}
        self.assertIn("integrations", keys)
        self.assertIn("admin_url", bridges[0])
        self.assertIn("super_bridge_path", bridges[0])
        self.assertIn("/super/operator-policy/", data.get("operator_policy", ""))
