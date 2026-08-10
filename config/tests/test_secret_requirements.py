"""Fail-closed secret enforcement: hosted deploys must not silently derive/skip
production-critical secrets (DJANGO_CRYPTOGRAPHY_KEY, MIGRATION_CLOUD_AUDIT_SIGNING_KEY).

MUST-FIRE: against the pre-fix tree ``config.secret_requirements`` does not exist, so
importing this module raises ImportError and every test errors.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.secret_requirements import require_secret_on_hosted


class RequireSecretOnHostedTests(SimpleTestCase):
    def test_hosted_missing_raises_with_name(self):
        for name in ("DJANGO_CRYPTOGRAPHY_KEY", "MIGRATION_CLOUD_AUDIT_SIGNING_KEY"):
            for missing in (None, ""):
                with self.subTest(name=name, value=repr(missing)):
                    with self.assertRaises(ImproperlyConfigured) as ctx:
                        require_secret_on_hosted(name, missing, is_hosted=True)
                    self.assertIn(name, str(ctx.exception))

    def test_hosted_present_returns_value(self):
        self.assertEqual(
            require_secret_on_hosted(
                "DJANGO_CRYPTOGRAPHY_KEY", "real-key", is_hosted=True
            ),
            "real-key",
        )

    def test_not_hosted_missing_is_noop_passthrough(self):
        # Local dev / CI / the test suite: never raise, even when unset.
        self.assertIsNone(
            require_secret_on_hosted("DJANGO_CRYPTOGRAPHY_KEY", None, is_hosted=False)
        )
        self.assertEqual(
            require_secret_on_hosted(
                "MIGRATION_CLOUD_AUDIT_SIGNING_KEY", "", is_hosted=False
            ),
            "",
        )

    def test_guidance_is_included_in_message(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            require_secret_on_hosted("X", None, is_hosted=True, guidance="Do the thing.")
        self.assertIn("Do the thing.", str(ctx.exception))

    def test_settings_boot_derives_key_in_non_hosted(self):
        # The wired settings must import cleanly in a non-hosted context (CI/tests):
        # CRYPTOGRAPHY_KEY falls back to SECRET_KEY rather than raising at boot.
        self.assertTrue(settings.CRYPTOGRAPHY_KEY)
