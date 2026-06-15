"""Regression seal: Setup Studio must stay a registered access module.

`setup_studio` is a real Django app (app_name="setup_studio", namespaced in config/urls.py).
If it is absent from MODULE_ACCESS_DEFAULTS, can_access_module() default-denies it for
EVERY tenant user (unknown module → deny) — which locked the whole Setup Studio out and
dropped newly-provisioned owners onto an "Access required" wall during onboarding.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.accounts.permissions import MODULE_ACCESS_DEFAULTS


class SetupStudioModuleAccessSeal(SimpleTestCase):
    def test_setup_studio_is_a_registered_module(self):
        self.assertIn(
            "setup_studio", MODULE_ACCESS_DEFAULTS,
            msg="setup_studio missing from MODULE_ACCESS_DEFAULTS → can_access_module "
                "default-denies it for everyone, blocking the Setup Studio onboarding flow.",
        )

    def test_admin_role_can_read_setup_studio(self):
        # ADMIN is the role a newly-provisioned school owner receives.
        self.assertIn("ADMIN", MODULE_ACCESS_DEFAULTS["setup_studio"].get("read", set()))

    def test_setup_studio_mirrors_studio_os_policy(self):
        # The onboarding studio should not be more permissive than its runtime sibling.
        self.assertEqual(
            MODULE_ACCESS_DEFAULTS["setup_studio"]["read"],
            MODULE_ACCESS_DEFAULTS["studio_os"]["read"],
        )
