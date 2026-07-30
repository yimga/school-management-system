"""North Star self-heal + founder dashboard contract (no live external services)."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.test_utils.http_clients import login_manager_client

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from northstar_self_heal_lib import (  # noqa: E402
    categorize_failure,
    write_ticket,
)


class NorthstarSelfHealUnitTests(TestCase):
    def test_classify_inventory_drift(self):
        self.assertEqual(
            categorize_failure("verify", "regenerate platform_inventory", ""),
            "inventory_drift",
        )

    def test_unsafe_permission_creates_ticket_file_not_product(self):
        with tempfile.TemporaryDirectory() as d:
            tickets = Path(d)
            path = write_ticket(
                tickets,
                category="permission_gap",
                command="python scripts/audit_security_surface.py",
                excerpt="403 permission",
                cause="expected in test",
                action="fix code",
                affected_files=[],
                risk="high",
                test_command="python manage.py test",
                timestamp="t0",
            )
            self.assertTrue(path.is_file())
            self.assertIn("403", path.read_text(encoding="utf-8"))

    def test_self_heal_report_json_status(self):
        out = {
            "status": "HUMAN_REVIEW_REQUIRED",
            "failures": [],
            "safe_fixes_applied": [],
        }
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "northstar_self_heal_report.json"
            p.write_text(json.dumps(out), encoding="utf-8")
            self.assertEqual(
                json.loads(p.read_text(encoding="utf-8"))["status"],
                "HUMAN_REVIEW_REQUIRED",
            )

    def test_parse_sot_north_star(self):
        from northstar_common import parse_sot_north_star_slice_status

        text = (
            "x (North Star slice 15 — t, 2026-04-27):** **DONE** —\n"
            "y (North Star slice 16 — t, 2026-04-27):** **PARTIAL** —\n"
        )
        st = parse_sot_north_star_slice_status(text)
        self.assertEqual(st[15], "DONE")
        self.assertEqual(st[16], "PARTIAL")


@override_settings(ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost"])
class FounderDashboardStripTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="founder_dash_op",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        # Manager-host operator page: confirmed device + verified MFA on a
        # manager-bound session (bare force_login bounces 302 through the MFA wall).
        self.client = login_manager_client(self.user, password="x" * 8)
        self.host = "manager.runmycampus.com"
        self.env = mock.patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_founder_dashboard_includes_markers(self):
        url = reverse("super:founder_dashboard")
        r = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200, msg=r.content[:500])
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-founder-dashboard=", body)
        self.assertIn("data-rmc-self-heal-status=", body)
        self.assertIn("data-rmc-observability-ledger=", body)
