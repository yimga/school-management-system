"""SINGLE_TENANT must be a real, env-driven setting — not an inert .env line.

Runbook gap (Gilead edge deployment): ``deploy/selfhost/.env.edge.example`` sets
``SINGLE_TENANT=True``, but ``config/settings.py`` never read it, so the attribute
did not exist and the "bare host resolves to the sole school" promise was dead —
``check_edge_readiness`` silently skipped its one-school coherence check and the
middleware helper could never fire.

Each test is written to FAIL before the settings.py fix:
  * the attribute was absent  -> hasattr(settings, "SINGLE_TENANT") was False,
    and reading settings.SINGLE_TENANT raised AttributeError.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.test import TestCase, override_settings

from apps.schools.models import School


class SingleTenantSettingTests(TestCase):
    def test_single_tenant_is_defined_and_boolean(self):
        # Before the fix settings.py never assigned SINGLE_TENANT: the attribute
        # did not exist (settings_test does `from .settings import *`).
        self.assertTrue(hasattr(settings, "SINGLE_TENANT"))
        self.assertIsInstance(settings.SINGLE_TENANT, bool)

    def test_single_tenant_defaults_false_off_the_edge(self):
        # No SINGLE_TENANT env in an ordinary run -> cloud/default posture is
        # unchanged, so multi-tenant dispatch is never disturbed.
        self.assertFalse(settings.SINGLE_TENANT)

    @override_settings(SINGLE_TENANT=True)
    def test_helper_resolves_the_sole_active_school_when_on(self):
        # Prove the value actually flows to the consumer the edge bare-host
        # promise depends on. Force exactly one active school.
        from apps.schools.middleware import _get_single_tenant_school

        uid = uuid.uuid4().hex[:8]
        School.objects.filter(is_active=True).update(is_active=False)
        sole = School.objects.create(
            name=f"Sole {uid}", slug=f"sole-{uid}", subdomain=f"sole{uid}",
            is_active=True, settings={},
        )
        self.assertEqual(_get_single_tenant_school(), sole)

    @override_settings(SINGLE_TENANT=False)
    def test_helper_is_inert_when_off(self):
        from apps.schools.middleware import _get_single_tenant_school

        uid = uuid.uuid4().hex[:8]
        School.objects.create(
            name=f"Off {uid}", slug=f"off-{uid}", subdomain=f"off{uid}",
            is_active=True, settings={},
        )
        self.assertIsNone(_get_single_tenant_school())
