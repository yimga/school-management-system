"""Both directions for scan_test_host_fidelity: what it must catch, and what it must not.

The must-NOT-fire half is the load-bearing half. 33 test files in this repo pass a
host urlconf to ``reverse()`` or ``get_resolver()``, which is correct as written --
those calls never touch middleware. A gate that flagged them would be reporting 41
findings of which 8 are real, and would be switched off within a week.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "scan_test_host_fidelity",
    Path(__file__).resolve().parents[1] / "scan_test_host_fidelity.py",
)
scanner = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(scanner)


class _ScannerCase(unittest.TestCase):
    """Write a throwaway test module and scan it.

    The file must live under ``REPO_ROOT`` -- ``scan_file`` reports paths via
    ``Path.relative_to(REPO_ROOT)``, which raises ValueError for anything outside it.
    """

    def findings_for(self, source: str) -> list[dict]:
        var_dir = scanner.REPO_ROOT / "var"
        var_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="test_hostfidelity_probe_",
            dir=var_dir,
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write(source)
            path = Path(handle.name)
        try:
            return scanner.scan_file(path)
        finally:
            path.unlink(missing_ok=True)


class MustFireTests(_ScannerCase):
    def test_tenant_urlconf_with_a_hostless_client_request(self):
        findings = self.findings_for(
            '@override_settings(ROOT_URLCONF="config.tenant_urls")\n'
            "class T(TestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/finance/reports/")\n'
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["declared_urlconf"], "config.tenant_urls")
        self.assertEqual(findings[0]["request_count"], 1)
        self.assertEqual(findings[0]["scope"], "T")

    def test_manager_and_public_urlconfs_count_too(self):
        for urlconf in ("config.manager_urls", "config.public_urls", "config.api_urls"):
            with self.subTest(urlconf=urlconf):
                findings = self.findings_for(
                    f'@override_settings(ROOT_URLCONF="{urlconf}")\n'
                    "class T(TestCase):\n"
                    "    def test_x(self):\n"
                    '        self.client.post("/x/")\n'
                )
                self.assertEqual(len(findings), 1)

    def test_settings_dict_splatted_into_the_decorator(self):
        """The urlconf is often a module constant, not a literal in the decorator."""
        findings = self.findings_for(
            '_TENANT = dict(ROOT_URLCONF="config.tenant_urls", ALLOWED_HOSTS=["*"])\n'
            "@override_settings(**_TENANT)\n"
            "class T(TestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/x/")\n'
        )
        self.assertEqual(len(findings), 1)

    def test_every_request_is_counted_not_just_the_first(self):
        findings = self.findings_for(
            '@override_settings(ROOT_URLCONF="config.tenant_urls")\n'
            "class T(TestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/a/")\n'
            '        self.client.post("/b/")\n'
            '        self.client.delete("/c/")\n'
        )
        self.assertEqual(findings[0]["request_count"], 3)


class MustNotFireTests(_ScannerCase):
    def test_a_host_header_anywhere_credits_the_file(self):
        findings = self.findings_for(
            '@override_settings(ROOT_URLCONF="config.tenant_urls")\n'
            "class T(TestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/x/", HTTP_HOST="s.runmycampus.com")\n'
        )
        self.assertEqual(findings, [])

    def test_reverse_only_files_are_not_findings(self):
        """reverse(urlconf=...) never goes through middleware -- it is correct."""
        findings = self.findings_for(
            "def test_x():\n"
            '    reverse("portal:home", urlconf="config.tenant_urls")\n'
            '    get_resolver("config.manager_urls")\n'
        )
        self.assertEqual(findings, [])

    def test_a_urlconf_that_is_not_host_split_is_ignored(self):
        for urlconf in ("config.urls", "apps.portal.tests.fixture_urls"):
            with self.subTest(urlconf=urlconf):
                findings = self.findings_for(
                    f'@override_settings(ROOT_URLCONF="{urlconf}")\n'
                    "class T(TestCase):\n"
                    "    def test_x(self):\n"
                    '        self.client.get("/x/")\n'
                )
                self.assertEqual(findings, [])

    def test_the_shared_login_helpers_credit_the_file(self):
        for helper in (
            "login_tenant_client",
            "login_manager_client",
            "login_tenant_admin_client",
        ):
            with self.subTest(helper=helper):
                findings = self.findings_for(
                    f"from apps.test_utils.http_clients import {helper}\n"
                    '@override_settings(ROOT_URLCONF="config.tenant_urls")\n'
                    "class T(TestCase):\n"
                    "    def test_x(self):\n"
                    f"        client = {helper}(u, password='p', host=h)\n"
                    '        client.get("/x/")\n'
                )
                self.assertEqual(findings, [])

    def test_the_tenant_host_base_class_credits_the_file(self):
        findings = self.findings_for(
            "from apps.test_utils.tenant_hosts import TenantHostTestCase\n"
            '@override_settings(ROOT_URLCONF="config.tenant_urls")\n'
            "class T(TenantHostTestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/x/")\n'
        )
        self.assertEqual(findings, [])

    def test_server_name_credits_the_file(self):
        """RequestFactory sets the host with SERVER_NAME, not HTTP_HOST."""
        findings = self.findings_for(
            '@override_settings(ROOT_URLCONF="config.tenant_urls")\n'
            "class T(TestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/x/", SERVER_NAME="s.runmycampus.com")\n'
        )
        self.assertEqual(findings, [])

    def test_a_reviewed_exception_is_honoured(self):
        findings = self.findings_for(
            "# test-host-fidelity-allow: asserts the developer surface on purpose\n"
            '@override_settings(ROOT_URLCONF="config.tenant_urls")\n'
            "class T(TestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/x/")\n'
        )
        self.assertEqual(findings, [])

    def test_an_unparseable_file_is_left_to_the_parse_gate(self):
        findings = self.findings_for(
            '@override_settings(ROOT_URLCONF="config.tenant_urls")\n'
            "class T(TestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/x/"\n'  # never closed
        )
        self.assertEqual(findings, [])

    def test_no_root_urlconf_declaration_is_not_a_finding(self):
        """Most tests never name a urlconf; they are out of scope, not compliant."""
        findings = self.findings_for(
            "class T(TestCase):\n"
            "    def test_x(self):\n"
            '        self.client.get("/x/")\n'
        )
        self.assertEqual(findings, [])


class LiveTreeTests(unittest.TestCase):
    def test_the_repository_scans_clean(self):
        """The seal. If this fails, a new test aims at a urlconf it will not reach."""
        findings = []
        for path in scanner._iter_test_files():
            findings.extend(scanner.scan_file(path))
        self.assertEqual(
            findings,
            [],
            "test files declare a host urlconf but never set a Host header:\n"
            + "\n".join(f"  {f['file']}:{f['line']}" for f in findings),
        )

    def test_the_scanner_actually_reaches_the_test_corpus(self):
        """A detector that scans nothing reports zero. Prove the corpus is non-empty."""
        self.assertGreater(len(list(scanner._iter_test_files())), 1000)


if __name__ == "__main__":
    unittest.main()
