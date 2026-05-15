"""Wave L2: CSP enforcement readiness preflight tests.

Covers:

1. Happy-path: middleware wired + report URI set + all required
   directives + no unsafe-inline / unsafe-eval in script-src → ready.
2. Each blocker fires individually when its precondition is absent.
3. style-src 'unsafe-inline' is a warning, not a blocker (intentional
   trade-off — see csp_readiness.py docstring).
4. CSP_EXTRA_SCRIPT_SRC tokens widen script-src but don't downgrade
   readiness (the rare-but-real case where ops add a CDN allowlist).
5. CLI exit semantics: 0 when ready, 1 when not.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.security.csp_readiness import (
    REQUIRED_DIRECTIVES,
    assess_csp_readiness,
)


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
class CspReadinessHappyPathTests(TestCase):

    def test_default_config_is_ready(self):
        report = assess_csp_readiness()
        self.assertTrue(
            report.ready,
            msg=(
                f"expected ready, got blockers: "
                f"middleware_wired={report.middleware_wired}, "
                f"report_uri={report.report_uri!r}, "
                f"missing={report.directives_missing}, "
                f"script_unsafe_inline={report.script_src_has_unsafe_inline}, "
                f"script_unsafe_eval={report.script_src_has_unsafe_eval}"
            ),
        )

    def test_required_directives_all_present(self):
        report = assess_csp_readiness()
        for directive in REQUIRED_DIRECTIVES:
            self.assertIn(directive, report.directives_present)
        self.assertEqual(report.directives_missing, [])

    def test_style_src_unsafe_inline_is_warning_not_blocker(self):
        report = assess_csp_readiness()
        # Default policy intentionally retains style-src 'unsafe-inline'.
        self.assertTrue(report.style_src_has_unsafe_inline)
        # But this does NOT block readiness.
        self.assertTrue(report.ready)


class CspReadinessBlockerTests(TestCase):
    """Each blocker fires individually when its precondition is absent."""

    @override_settings(
        MIDDLEWARE=(),  # not wired
        CSP_REPORT_URI="/security/csp-report/",
    )
    def test_middleware_not_wired_blocks(self):
        report = assess_csp_readiness()
        self.assertFalse(report.middleware_wired)
        self.assertFalse(report.ready)

    @override_settings(
        MIDDLEWARE=(_MW_TARGET,),
        CSP_REPORT_URI="",
    )
    def test_blank_report_uri_blocks(self):
        report = assess_csp_readiness()
        self.assertEqual(report.report_uri, "")
        self.assertFalse(report.ready)

    @override_settings(
        MIDDLEWARE=(_MW_TARGET,),
        CSP_REPORT_URI="/security/csp-report/",
        CSP_EXTRA_SCRIPT_SRC=("'unsafe-inline'",),
    )
    def test_script_unsafe_inline_blocks(self):
        report = assess_csp_readiness()
        self.assertTrue(report.script_src_has_unsafe_inline)
        self.assertFalse(report.ready)

    @override_settings(
        MIDDLEWARE=(_MW_TARGET,),
        CSP_REPORT_URI="/security/csp-report/",
        CSP_EXTRA_SCRIPT_SRC=("'unsafe-eval'",),
    )
    def test_script_unsafe_eval_blocks(self):
        report = assess_csp_readiness()
        self.assertTrue(report.script_src_has_unsafe_eval)
        self.assertFalse(report.ready)


@override_settings(
    MIDDLEWARE=(_MW_TARGET,),
    CSP_REPORT_URI="/security/csp-report/",
    CSP_EXTRA_SCRIPT_SRC=("https://cdn.example.com",),  # safe widening
    CSP_EXTRA_STYLE_SRC=(),
    CSP_EXTRA_IMG_SRC=(),
    CSP_EXTRA_CONNECT_SRC=(),
    CSP_EXTRA_FRAME_ANCESTORS=(),
)
class CspReadinessCdnAllowlistTests(TestCase):
    """Adding a CDN origin via CSP_EXTRA_SCRIPT_SRC must not downgrade
    readiness — that's the whole point of the allowlist setting.
    """

    def test_cdn_allowlist_keeps_ready(self):
        report = assess_csp_readiness()
        self.assertTrue(report.ready)
        self.assertFalse(report.script_src_has_unsafe_inline)
        self.assertFalse(report.script_src_has_unsafe_eval)


class CspReadinessCommandTests(TestCase):
    """CLI exit semantics."""

    @override_settings(
        MIDDLEWARE=(_MW_TARGET,),
        CSP_REPORT_URI="/security/csp-report/",
        CSP_EXTRA_SCRIPT_SRC=(),
        CSP_EXTRA_STYLE_SRC=(),
        CSP_EXTRA_IMG_SRC=(),
        CSP_EXTRA_CONNECT_SRC=(),
        CSP_EXTRA_FRAME_ANCESTORS=(),
    )
    def test_command_exits_0_when_ready(self):
        out = StringIO()
        call_command("verify_csp_readiness", stdout=out)
        self.assertIn("READY", out.getvalue())

    @override_settings(
        MIDDLEWARE=(),  # blocker
        CSP_REPORT_URI="/security/csp-report/",
    )
    def test_command_exits_1_when_not_ready(self):
        with self.assertRaises(SystemExit) as cm:
            call_command("verify_csp_readiness", "--quiet", stdout=StringIO())
        self.assertEqual(cm.exception.code, 1)

    @override_settings(
        MIDDLEWARE=(_MW_TARGET,),
        CSP_REPORT_URI="",  # blocker
    )
    def test_command_blocks_on_blank_report_uri(self):
        with self.assertRaises(SystemExit):
            call_command("verify_csp_readiness", "--quiet", stdout=StringIO())
