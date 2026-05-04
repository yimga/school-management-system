"""Operational UX — no dummy hash anchors on audited operational templates (Agent 4 CTA cleanup)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]

# Operational / command-center surfaces (Agent 4 scope); extend when adding centers.
AUDITED_OPERATIONAL_TEMPLATE_RELS: tuple[str, ...] = (
    "templates/finance/dashboard.html",
    "templates/finance/payment_readiness_dashboard.html",
    "templates/analytics/dashboard.html",
    "templates/analytics/governed_report_builder.html",
    "templates/analytics/governed_saved_report_detail.html",
    "templates/automation/outcomes_console.html",
    "templates/automation/visual_workflow_designer.html",
    "templates/events/event_console.html",
    "templates/events/event_dlq.html",
    "templates/portal/offline_sync_queue.html",
    "templates/portal/offline_sync_conflicts.html",
    "templates/siteconfig/dashboard_hub.html",
    "templates/siteconfig/dashboard_configuration_hub.html",
    "templates/partials/onboarding_what_next.html",
    "templates/portal/teacher_bulk_capture_hub.html",
)


class CtaCleanupTemplateAuditTests(SimpleTestCase):
    def test_static_js_tree_avoids_javascript_void_stub(self):
        """Optional hygiene: operational UX avoids `javascript:void(0)` in first-party static JS."""
        static_root = REPO / "static"
        if not static_root.is_dir():
            return
        bad: list[str] = []
        for path in static_root.rglob("*.js"):
            if any(x in path.parts for x in ("node_modules", "vendor")):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "javascript:void(0)" in text:
                bad.append(str(path.relative_to(REPO)))
        self.assertFalse(bad, msg="; ".join(bad[:25]))

    def test_audited_operational_templates_no_dummy_ctas(self):
        for rel in AUDITED_OPERATIONAL_TEMPLATE_RELS:
            path = REPO / rel
            self.assertTrue(path.is_file(), msg=f"missing {rel}")
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('href="#"', text, msg=rel)
            self.assertNotIn('action="#"', text, msg=rel)
            self.assertNotIn("javascript:void(0)", text, msg=rel)
            if rel.endswith("onboarding_what_next.html"):
                self.assertIn("data-tour-trigger", text, msg=rel)
            if rel.endswith("teacher_bulk_capture_hub.html"):
                self.assertIn("teacher_bulk_capture_hub", text, msg=rel)
