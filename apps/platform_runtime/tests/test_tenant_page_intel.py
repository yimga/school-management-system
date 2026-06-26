"""Pure contract tests for the TENANT page-intelligence flow.

Mirror of the manager page-intel: ``tenant_flow_steps`` returns the curated,
role-scoped onward steps FROM a tenant page. Pure — no DB, no URLconf (URL
resolution + current-page exclusion live in the action_engine consumer).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.control_plane_page_intel import (
    TENANT_BUCKET_FLOW,
    TENANT_PAGES,
    TENANT_SECTION_DEFAULT_FLOW,
    resolve_tenant_page,
    tenant_flow_steps,
)


class ResolveTenantPageTests(SimpleTestCase):
    def test_mapped_route_returns_entry(self):
        entry = resolve_tenant_page("portal:teacher_dashboard_alias")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["title"], "Teacher home")
        self.assertIn("flow", entry)

    def test_unmapped_and_empty_return_none(self):
        self.assertIsNone(resolve_tenant_page("portal:nope"))
        self.assertIsNone(resolve_tenant_page(""))


class TenantFlowStepsTests(SimpleTestCase):
    def _viewnames(self, steps):
        return [s["viewname"] for s in steps]

    def test_mapped_page_uses_its_curated_flow(self):
        steps = tenant_flow_steps("portal:teacher_dashboard_alias", "portal", "teacher")
        self.assertEqual(
            self._viewnames(steps),
            ["portal:teacher_attendance", "portal:teacher_gradebook", "portal:teacher_timetable"],
        )

    def test_steps_never_include_the_current_page(self):
        # teacher_attendance's flow leads to gradebook/assignments/timetable; the
        # page itself must never be re-offered even if it appeared in a flow tuple.
        steps = tenant_flow_steps("portal:teacher_gradebook", "portal", "teacher")
        self.assertNotIn("portal:teacher_gradebook", self._viewnames(steps))

    def test_unmapped_page_falls_back_to_bucket_flow(self):
        # A teacher on an unmapped portal page still gets teacher-relevant steps.
        steps = tenant_flow_steps("portal:some_unmapped_page", "portal", "teacher")
        self.assertEqual(self._viewnames(steps), list(TENANT_BUCKET_FLOW["teacher"]))

    def test_bucket_scoping_differs_per_role(self):
        teacher = self._viewnames(
            tenant_flow_steps("portal:unmapped", "portal", "teacher")
        )
        parent = self._viewnames(
            tenant_flow_steps("portal:unmapped", "portal", "parent")
        )
        self.assertNotEqual(teacher, parent)
        self.assertEqual(parent, list(TENANT_BUCKET_FLOW["parent"]))

    def test_audiences_gate_falls_back_when_bucket_excluded(self):
        # A parent landing on a teacher-only mapped page does NOT get the teacher
        # curated flow — it falls back to the parent bucket flow.
        steps = tenant_flow_steps("portal:teacher_dashboard_alias", "portal", "parent")
        self.assertEqual(self._viewnames(steps), list(TENANT_BUCKET_FLOW["parent"]))

    def test_founder_and_staff_share_admin_flow(self):
        admin = self._viewnames(tenant_flow_steps("x:y", "x", "admin"))
        founder = self._viewnames(tenant_flow_steps("x:y", "x", "founder"))
        staff = self._viewnames(tenant_flow_steps("x:y", "x", "staff"))
        self.assertEqual(admin, founder)
        self.assertEqual(admin, staff)

    def test_section_default_when_bucket_unknown(self):
        steps = tenant_flow_steps("finance:weird_page", "finance", "anonymous")
        self.assertEqual(self._viewnames(steps), list(TENANT_SECTION_DEFAULT_FLOW["finance"]))

    def test_empty_when_nothing_maps(self):
        self.assertEqual(tenant_flow_steps("zzz:zzz", "zzz", "anonymous"), [])

    def test_targets_only_in_flow_get_humanised_label(self):
        # teacher_lesson_notes is a flow TARGET but not a TENANT_PAGES key →
        # humanised title, never a crash / empty title.
        steps = tenant_flow_steps("portal:teacher_assignments", "portal", "teacher")
        by_view = {s["viewname"]: s for s in steps}
        self.assertIn("portal:teacher_lesson_notes", by_view)
        self.assertEqual(by_view["portal:teacher_lesson_notes"]["title"], "Teacher Lesson Notes")
        self.assertTrue(by_view["portal:teacher_lesson_notes"]["body"])


class TenantMapWellFormednessTests(SimpleTestCase):
    def _all_viewnames(self):
        names = set(TENANT_PAGES)
        for entry in TENANT_PAGES.values():
            names.update(entry.get("flow", ()))
        for flow in TENANT_BUCKET_FLOW.values():
            names.update(flow)
        for flow in TENANT_SECTION_DEFAULT_FLOW.values():
            names.update(flow)
        return names

    def test_every_viewname_is_namespaced(self):
        for vn in self._all_viewnames():
            self.assertIn(":", vn, vn)
            ns, name = vn.split(":", 1)
            self.assertTrue(ns and name, vn)

    def test_audiences_are_lowercase_buckets(self):
        allowed = {"teacher", "parent", "student", "admin", "founder", "staff", "all"}
        for vn, entry in TENANT_PAGES.items():
            for aud in entry.get("audiences", ()):  # frozenset
                self.assertIn(aud, allowed, f"{vn}:{aud}")
                self.assertEqual(aud, aud.lower(), aud)
