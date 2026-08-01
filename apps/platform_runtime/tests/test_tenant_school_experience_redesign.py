from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class TenantSchoolExperienceRedesignTests(SimpleTestCase):
    def test_school_settings_has_title_primary_action_tenant_safety_and_mobile_marker(self):
        # MAX operator↔tenant parity wave (6a155f984): school_configuration_center
        # moved off the bespoke operational-center-frame to the shared masthead +
        # a permission-gated section table (primary action/title/purpose now flow
        # through rmc_page_masthead.html via build_masthead). Assert the surviving
        # contract: apple-class tenant-school-admin scope, shared masthead, the
        # per-section permission gate (tenant-safety), the mobile marker, and no
        # operator-plane leakage.
        text = (ROOT / "templates" / "platform_runtime" / "school_configuration_center.html").read_text(encoding="utf-8")
        self.assertIn('data-apple-class-tenant-school-admin="1"', text)
        self.assertIn("rmc_page_masthead.html", text)
        self.assertIn("can_access_permission", text)
        self.assertIn("data-school-configuration-section", text)
        self.assertIn("data-world-class-mobile-layout", text)
        self.assertNotIn("system_closure_map", text)
        self.assertNotIn("global registries", text.lower())

    def test_tenant_setup_surfaces_show_external_blockers_honestly(self):
        for name in ("tenant_blueprint_setup.html", "tenant_pack_setup.html"):
            with self.subTest(name=name):
                text = (ROOT / "templates" / "platform_runtime" / name).read_text(encoding="utf-8")
                self.assertIn("rmc_operational_center_frame.html", text)
                self.assertIn('data-rmc-operational-workbench="1"', text)
                self.assertIn("external", text.lower())
                self.assertIn("approval", text.lower())
                self.assertIn("world_class_readiness_meter.html", text)

    def test_tenant_pack_setup_uses_the_approved_full_canvas_contract(self):
        template = (
            ROOT / "templates" / "platform_runtime" / "tenant_pack_setup.html"
        ).read_text(encoding="utf-8")
        css = (ROOT / "static" / "css" / "rmc-tenant-pack-workbench.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('data-rmc-full-canvas-catalog="tenant-pack"', template)
        self.assertIn('data-rmc-genuine-pack-action="1"', template)
        self.assertIn("components/pagination.html", template)
        self.assertNotIn('class="panel', template)
        self.assertNotIn('class="grid', template)
        self.assertNotIn('class="card', template)
        self.assertNotIn("page-shell", template)
        self.assertIn(
            "grid-template-columns: minmax(0, 1fr) minmax(19rem, 28%);", css
        )
        self.assertIn("@media (max-width: 1024px)", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", css)

    def test_audited_operator_workbenches_have_one_shared_steering_owner(self):
        for name in (
            "super_provision_queue.html",
            "super_support_live_console.html",
        ):
            with self.subTest(name=name):
                text = (ROOT / "templates" / "schools" / name).read_text(
                    encoding="utf-8"
                )
                self.assertIn("rmc_operational_center_frame.html", text)
                self.assertIn("block cp_workspace_header", text)
                self.assertNotIn("<h1", text.lower())

    def test_audited_operator_tables_wrap_long_values_instead_of_clipping(self):
        paths = (
            ROOT / "templates" / "super" / "ai_line_intent_coverage.html",
            ROOT / "templates" / "super" / "merges" / "index.html",
            ROOT / "templates" / "super" / "school_batches" / "index.html",
            ROOT / "templates" / "super" / "transfers" / "cases_index.html",
        )
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("overflow: hidden", text)
                self.assertIn("overflow-wrap: anywhere", text)
