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
    humanised_page_help,
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

    def test_every_step_has_nonempty_title_and_body(self):
        # No mapped page (or bucket/section fallback) may ever produce a step with
        # an empty title/body — whether the target is a curated key or humanised.
        flows = (
            [(vn, vn.split(":", 1)[0], "admin") for vn in TENANT_PAGES]
            + [("x:unmapped", "x", b) for b in TENANT_BUCKET_FLOW]
            + [("y:unmapped", ns, "anonymous") for ns in TENANT_SECTION_DEFAULT_FLOW]
        )
        for view_name, namespace, bucket in flows:
            for step in tenant_flow_steps(view_name, namespace, bucket):
                self.assertTrue(step["title"], f"{view_name}->{step['viewname']}")
                self.assertTrue(step["body"], f"{view_name}->{step['viewname']}")
                self.assertIsInstance(step["priority"], int)

    def test_humanised_fallback_formats_unmapped_target(self):
        # The curated map now covers every referenced target, but the fallback
        # path must still format an unmapped viewname (future-proofing).
        title, body = humanised_page_help("portal:some_new_page", "portal")
        self.assertEqual(title, "Some New Page")
        self.assertIn("your school portal", body)

    def test_forum_cross_role_page_falls_through_to_bucket_flow(self):
        # forum_home has an empty flow on purpose: when you are ON it, the role
        # bucket flow leads, so a teacher and a student get different next steps.
        teacher = self._viewnames(tenant_flow_steps("portal:forum_home", "portal", "teacher"))
        student = self._viewnames(tenant_flow_steps("portal:forum_home", "portal", "student"))
        self.assertEqual(teacher, list(TENANT_BUCKET_FLOW["teacher"]))
        self.assertEqual(student, list(TENANT_BUCKET_FLOW["student"]))


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
