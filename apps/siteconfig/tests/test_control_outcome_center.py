"""Phase 3 — outcome registry resolves on manager urlconf."""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.control_outcome_center import (
    OUTCOME_GROUP_SPECS,
    build_control_studio_rail_sections,
    build_operator_control_model_for_request,
    build_outcome_groups_for_request,
)


class ControlOutcomeCenterTests(SimpleTestCase):
    def test_nine_groups_resolve_with_incidents_link(self):
        rf = RequestFactory().get("/")
        rf.urlconf = "config.manager_urls"
        rf.user = AnonymousUser()
        groups = build_outcome_groups_for_request(rf)
        self.assertEqual(len(groups), 9)
        ids = {g["id"] for g in groups}
        self.assertEqual(
            ids,
            {
                "platform_health",
                "tenants_schools",
                "runtime_policies",
                "packages_marketplace",
                "brand_experience",
                "billing_commercial",
                "security_access",
                "observability",
                "registries_localization",
            },
        )
        ph = next(g for g in groups if g["id"] == "platform_health")
        labels = {x["label"] for x in ph["links"]}
        self.assertIn("Incidents", labels)
        rp = next(g for g in groups if g["id"] == "runtime_policies")
        rp_labels = {x["label"] for x in rp["links"]}
        self.assertIn("Diff / impact summary", rp_labels)
        self.assertIn("Rollback (Control)", rp_labels)
        rollback = next(x for x in rp["links"] if x["label"] == "Rollback (Control)")
        self.assertIn("mode=control", rollback["url"])
        # Display sources use canonical labels
        self.assertTrue(all(isinstance(s, str) for x in rp["links"] for s in x["sources"]))

    def test_spec_count_matches_zip_plan(self):
        self.assertEqual(len(OUTCOME_GROUP_SPECS), 9)

    def test_control_studio_rail_sections_matches_nine_groups(self):
        rf = RequestFactory().get("/studio/control/")
        rf.urlconf = "config.manager_urls"
        rf.user = AnonymousUser()
        sections = build_control_studio_rail_sections(rf)
        full = build_outcome_groups_for_request(rf)
        self.assertEqual(len(sections), 9)
        self.assertEqual(sections, full)
        for sec in sections:
            self.assertTrue(sec.get("links"))

    def test_tenant_request_still_resolves_super_via_manager_fallback(self):
        """Outcome registry uses manager urlconf fallback when tenant resolver lacks super: names."""
        rf = RequestFactory().get("/")
        rf.urlconf = "config.tenant_urls"
        rf.user = AnonymousUser()
        groups = build_outcome_groups_for_request(rf)
        self.assertEqual(len(groups), 9)

    def test_operator_control_model_six_steps_on_manager(self):
        """Phase 3 operator model: all six steps resolve with primary + evidence URLs."""
        rf = RequestFactory().get("/")
        rf.urlconf = "config.manager_urls"
        rf.user = AnonymousUser()
        steps = build_operator_control_model_for_request(rf)
        self.assertEqual(len(steps), 6)
        ids = [s["id"] for s in steps]
        self.assertEqual(
            ids,
            [
                "capability_families",
                "grouped_controls",
                "impact_summaries",
                "source_tracing",
                "staged_changes",
                "publish_rollback",
            ],
        )
        pub = next(s for s in steps if s["id"] == "publish_rollback")
        rb = next(r for r in pub["related"] if "Rollback" in r["label"])
        self.assertIn("mode=control", rb["url"])
        for s in steps:
            self.assertTrue(s["primary"]["url"])
            self.assertIn("stability", s["primary"])
