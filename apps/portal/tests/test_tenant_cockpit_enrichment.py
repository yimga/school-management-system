"""Tenant cockpit enrichment — parent child context (wave 3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.accounts.models import User
from apps.portal.tenant_cockpit_enrichment import (
    _hydrate_workspace_context_tenant,
    enrich_tenant_cockpit_for_request,
)
from apps.portal.tenant_role_home import (
    is_tp_v3_tenant_shell_request,
    tp_v3_role_home_shell_context,
)


class TenantShellContextTests(SimpleTestCase):
    def test_tenant_shell_true_for_authenticated_tenant(self):
        req = MagicMock()
        req.public_host_kind = "tenant"
        req.user.is_authenticated = True
        req.GET = {}
        req.resolver_match = MagicMock(url_name="cahier_list", namespace="portal")
        self.assertTrue(is_tp_v3_tenant_shell_request(req))

    def test_shell_context_includes_tenant_shell_flag(self):
        req = MagicMock()
        req.public_host_kind = "tenant"
        req.user.is_authenticated = True
        req.user.role = "TEACHER"
        req.GET = {}
        match = MagicMock()
        match.url_name = "teacher_dashboard"
        req.resolver_match = match
        ctx = tp_v3_role_home_shell_context(req)
        self.assertTrue(ctx["tp_v3_tenant_shell"])
        self.assertTrue(ctx["tp_v3_role_home"])


class WorkspaceContextHydrationTests(SimpleTestCase):
    def test_parent_hydration_enables_section(self):
        student = MagicMock()
        student.pk = 7
        student.first_name = "Sam"
        student.last_name = "Ade"
        student.get_full_name.return_value = "Sam Ade"
        student.classroom = None
        student.academic_year_label = ""

        link = MagicMock()
        link.student = student

        req = MagicMock()
        req.user.role = User.Role.PARENT
        req.user.is_authenticated = True

        with patch(
            "apps.portal.services.guardian_student_links",
            return_value=[link],
        ):
            with patch(
                "apps.portal.tenant_cockpit_enrichment.get_guardian_child_ids",
                return_value={7},
            ):
                with patch(
                    "apps.portal.tenant_cockpit_enrichment.get_active_child_id",
                    return_value=7,
                ):
                    with patch(
                        "apps.portal.tenant_cockpit_enrichment.reverse",
                        return_value="/switch/",
                    ):
                        out = _hydrate_workspace_context_tenant(
                            req, {"enabled": False}
                        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["child"]["name"], "Sam Ade")

    def test_enrich_merges_workspace_section(self):
        req = MagicMock()
        req.user.role = User.Role.TEACHER
        cockpit = {"workspace_context_tenant": {"enabled": False}}
        out = enrich_tenant_cockpit_for_request(req, cockpit)
        self.assertFalse(out["workspace_context_tenant"]["enabled"])
