"""Tenant + platform AI governance (School.settings['ai_policy'])."""

from __future__ import annotations

import os
import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.ai_governance import (
    get_public_ai_governance_context,
    resolve_effective_enabled,
    resolve_effective_external_network,
)
from apps.platform_runtime.ai_providers import get_ai_runtime_config
from apps.schools.models import School


class AIGovernanceTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.school = School.objects.create(
            name="Gov Test",
            slug=f"gt-{uuid.uuid4().hex[:8]}",
            subdomain=f"gt-{uuid.uuid4().hex[:8]}",
            is_active=True,
            settings={},
        )
        self.user = User.objects.create_user(
            username=f"g_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
        )

    def test_tenant_explicit_disable_when_global_on(self):
        prev = os.environ.get("RUNMYCAMPUS_AI_ENABLED")
        os.environ["RUNMYCAMPUS_AI_ENABLED"] = "1"
        try:
            self.school.settings = {"ai_policy": {"tenant_ai_enabled": False}}
            self.school.save(update_fields=["settings"])
            self.assertFalse(resolve_effective_enabled(school=self.school))
            cfg = get_ai_runtime_config(school=self.school)
            self.assertFalse(cfg["enabled"])
        finally:
            if prev is None:
                os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
            else:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    def test_external_requires_tenant_opt_in_when_school_present(self):
        prev_e = os.environ.get("RUNMYCAMPUS_AI_ALLOW_EXTERNAL")
        os.environ["RUNMYCAMPUS_AI_ALLOW_EXTERNAL"] = "1"
        try:
            self.school.settings = {"ai_policy": {}}
            self.school.save(update_fields=["settings"])
            self.assertFalse(resolve_effective_external_network(school=self.school))
            self.school.settings = {
                "ai_policy": {"allow_external_providers": True},
            }
            self.school.save(update_fields=["settings"])
            self.assertTrue(resolve_effective_external_network(school=self.school))
        finally:
            if prev_e is None:
                os.environ.pop("RUNMYCAMPUS_AI_ALLOW_EXTERNAL", None)
            else:
                os.environ["RUNMYCAMPUS_AI_ALLOW_EXTERNAL"] = prev_e

    def test_public_governance_context_safe(self):
        ctx = get_public_ai_governance_context(school=self.school)
        self.assertIn("effective_ai_enabled", ctx)
        self.assertIn("external_student_pii_allowed", ctx)
        self.assertNotIn("secret", str(ctx))
