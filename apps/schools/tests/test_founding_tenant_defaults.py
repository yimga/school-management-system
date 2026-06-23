"""Founding-tenant bootstrap defaults (env cascade, no gilead hardcoding)."""

from __future__ import annotations

import os
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.schools.founding_tenant_defaults import (
    founding_tenant_env_explicit,
    resolve_founding_tenant_name,
    resolve_founding_tenant_slug,
    resolve_founding_tenant_subdomain,
)


class FoundingTenantDefaultsTests(SimpleTestCase):
    def test_defaults_to_demo_school_when_env_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_founding_tenant_slug(), "demo-school")
            self.assertEqual(
                resolve_founding_tenant_name(slug="demo-school"), "Demo School"
            )
            self.assertEqual(
                resolve_founding_tenant_subdomain(slug="demo-school"), "demo-school"
            )

    def test_env_overrides(self):
        env = {
            "DEFAULT_TENANT_SLUG": "acme-academy",
            "DEFAULT_TENANT_NAME": "Acme Academy International",
            "DEFAULT_TENANT_SUBDOMAIN": "acme",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            slug = resolve_founding_tenant_slug()
            self.assertEqual(slug, "acme-academy")
            self.assertEqual(
                resolve_founding_tenant_name(slug=slug),
                "Acme Academy International",
            )
            self.assertEqual(resolve_founding_tenant_subdomain(slug=slug), "acme")
            self.assertTrue(founding_tenant_env_explicit())

    def test_invalid_slug_raises(self):
        with self.assertRaises(ValueError):
            resolve_founding_tenant_slug(override="NOT VALID")

    @override_settings(DEBUG=True)
    def test_command_importable(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command(
            "ensure_founding_tenant",
            slug="unit-test-tenant",
            dry_run=True,
            stdout=out,
        )
        self.assertIn("unit-test-tenant", out.getvalue())
