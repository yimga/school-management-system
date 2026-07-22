"""Phase A must ensure platform SiteSettings exists before portal login."""

from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase

from apps.schools.models import School
from apps.schools.tasks import _activate_portal_phase_a

_PROBE = "apps.schools.tenant_workspace.tenant_workspace_exists"
_ENSURE = "apps.platform_runtime.helpers.get_platform_site_settings_record"


class PhaseASiteSettingsEnsureTests(TestCase):
    def test_activate_portal_phase_a_ensures_site_settings(self):
        slug = f"ss-ensure-{uuid.uuid4().hex[:8]}"
        school = School.objects.create(
            name="SS Ensure",
            slug=slug,
            subdomain=slug,
            is_active=False,
        )
        with (
            mock.patch(_PROBE, return_value=True),
            mock.patch(_ENSURE) as ensure_ss,
            mock.patch("apps.schools.tasks.ensure_school_plan"),
        ):
            _activate_portal_phase_a(
                school,
                school_id=str(school.pk),
                contact_email="owner@example.com",
                admin_user=None,
                wf_run=None,
                pulse=lambda *a, **k: None,
            )
            ensure_ss.assert_any_call(create=True)
            self.assertGreaterEqual(ensure_ss.call_count, 1)
        school.refresh_from_db()
        self.assertTrue(school.is_active)
        self.assertTrue(
            ((school.settings or {}).get("provisioning") or {}).get("phase_a_complete")
        )
