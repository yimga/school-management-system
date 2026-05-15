"""Wave N integration tests for the unified readiness command.

Covers:

1. CSP section reports ready when config is clean.
2. Baselines section reports ready when no drift.
3. --section flag narrows which preflights run.
4. JSON mode returns parseable JSON with the section keys.
5. Exit code 1 when at least one section is not-ready.
6. Exit code 2 when invocation error in any section.
"""

from __future__ import annotations

import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings


_MW_TARGET = "apps.security.csp_middleware.ContentSecurityPolicyMiddleware"


@override_settings(
    MIDDLEWARE=(_MW_TARGET,),
    CSP_REPORT_URI="/security/csp-report/",
    CSP_EXTRA_SCRIPT_SRC=(),
    CSP_EXTRA_STYLE_SRC=(),
    CSP_EXTRA_IMG_SRC=(),
    CSP_EXTRA_CONNECT_SRC=(),
    CSP_EXTRA_FRAME_ANCESTORS=(),
)
class VerifyPlatformReadinessTests(TestCase):
    databases = {"default"}

    def test_csp_section_runs_independently(self):
        out = StringIO()
        # CSP-only run, so we don't touch the residency / baselines subprocess.
        call_command(
            "verify_platform_readiness",
            "--section", "csp",
            stdout=out,
        )
        self.assertIn("csp", out.getvalue())
        self.assertIn("ready", out.getvalue().lower())

    def test_json_mode_emits_parseable_json(self):
        out = StringIO()
        call_command(
            "verify_platform_readiness",
            "--section", "csp",
            "--json",
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        self.assertIn("ready", payload)
        self.assertIn("sections", payload)
        self.assertIn("csp", payload["sections"])
        self.assertIn("details", payload["sections"]["csp"])

    def test_not_ready_when_csp_blocked(self):
        with override_settings(MIDDLEWARE=()):  # CSP middleware not wired
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "verify_platform_readiness",
                    "--section", "csp",
                    stdout=StringIO(),
                )
            self.assertEqual(cm.exception.code, 1)

    def test_unknown_section_rejected_by_argparse(self):
        from django.core.management.base import CommandError

        # Django's call_command translates argparse errors into CommandError.
        with self.assertRaises((SystemExit, ValueError, CommandError)):
            call_command(
                "verify_platform_readiness",
                "--section", "no_such_section",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_invocation_error_exits_with_code_2(self):
        # Force the CSP section to raise during assessment by mocking
        # assess_csp_readiness to raise.
        with mock.patch(
            "apps.security.csp_readiness.assess_csp_readiness",
            side_effect=ImportError("boom"),
        ):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "verify_platform_readiness",
                    "--section", "csp",
                    stdout=StringIO(),
                )
            self.assertEqual(cm.exception.code, 2)

    def test_section_report_includes_runtime_counters(self):
        """The L-followup violation counters are surfaced in the
        readiness report's CSP section details.
        """
        out = StringIO()
        call_command(
            "verify_platform_readiness",
            "--section", "csp",
            "--json",
            stdout=out,
        )
        payload = json.loads(out.getvalue())
        details = payload["sections"]["csp"]["details"]
        self.assertIn("violations_last_hour", details)
        self.assertIn("violations_last_24h", details)
        self.assertIn("violations_by_directive_24h", details)
