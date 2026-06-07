"""Legacy seed_first_party_apps PackageVersion payloads are non-empty."""

from django.core.management import call_command
from django.test import TestCase

from apps.packages.first_party_package_payloads import (
    FIRST_PARTY_APP_DEFINITIONS,
    build_first_party_package_payload,
    first_party_package_rows,
)
from apps.packages.models import PackageVersion


class FirstPartyPackagePayloadTests(TestCase):
    def test_build_payload_always_non_empty(self):
        for item in FIRST_PARTY_APP_DEFINITIONS:
            pid = item["package_id"]
            payload = build_first_party_package_payload(
                package_id=pid,
                version=item.get("version") or "1.0",
                changelog_summary=item.get("changelog_summary") or "",
            )
            self.assertTrue(payload, msg=pid)
            section = next(iter(payload.values()))
            self.assertEqual(section.get("package_id"), pid, msg=pid)

    def test_seed_command_creates_all_legacy_packages(self):
        call_command("seed_first_party_apps", verbosity=0)
        for item in FIRST_PARTY_APP_DEFINITIONS:
            pid = item["package_id"]
            ver = str(item.get("version") or "1.0")
            pv = PackageVersion.objects.filter(package_id=pid, version=ver).first()
            self.assertIsNotNone(pv, msg=pid)
            self.assertTrue(pv.payload_sections, msg=pid)

    def test_rows_count_matches_definitions(self):
        rows = first_party_package_rows()
        self.assertEqual(len(rows), len(FIRST_PARTY_APP_DEFINITIONS))
