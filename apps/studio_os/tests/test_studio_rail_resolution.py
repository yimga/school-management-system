"""Every Studio mode rail target must resolve (reverse or deep_links path)."""

from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from apps.studio_os.deep_links import _PATHS, studio_resolve_url

# All view names used by studio_shell rails (experience, launch, automation, output, control)
_STUDIO_RAIL_VIEWNAMES = frozenset(
    {
        "siteconfig:theme_colors",
        "studio_os:experience",
        "siteconfig:school_theme_settings",
        "studio_os:experience_packs",
        "siteconfig:brand_import_from_url",
        "studio_os:experience_compare",
        "studio_os:experience_recommendations",
        "studio_os:experience_theme_tokens",
        "studio_os:experience_portal_shell_layouts",
        "studio_os:experience_dashboard_visual_packs",
        "studio_os:experience_school_website_blocks",
        "studio_os:experience_communication_style_packs",
        "siteconfig:guided_onboarding",
        "super:create_school_wizard",
        "studio_os:launch_select_plan",
        "siteconfig:get_blueprints",
        "automation:outcomes_console",
        "studio_os:automation",
        "studio_os:workflow_center",
        "siteconfig:workflow_flow_gallery",
        "studio_os:approval_hub",
        "studio_os:automation_dependency_graph",
        "studio_os:automation_workflow_health",
        "studio_os:automation_conflict_detection",
        "studio_os:automation_staged_activation",
        "studio_os:automation_replay_rollback",
        "studio_os:automation_visual_builder",
        "studio_os:automation_natural_language_workflow",
        "studio_os:automation_simulation_engine",
        "studio_os:output",
        "portal:document_library_manage",
        "siteconfig:reportcard_builder",
        "studio_os:output_dependency_graph",
        "studio_os:output_branding_inheritance",
        "studio_os:output_policy_registry",
        "studio_os:system_config_console",
        "siteconfig:feature_control_panel",
        "siteconfig:feature_control_audit",
        "super:runtime_inspector",
        "metadata:metadata_governance",
        "metadata:metadata_lineage_graph",
        "apicenter:dashboard",
        "super:policy_diff",
        "super:billing_dashboard",
        "studio_os:control_impact",
        "studio_os:ai_cleanup",
    }
)


class StudioRailResolutionTests(TestCase):
    def test_every_rail_viewname_has_path_fallback(self):
        for vn in _STUDIO_RAIL_VIEWNAMES:
            with self.subTest(viewname=vn):
                self.assertIn(
                    vn,
                    _PATHS,
                    f"Add {vn} to deep_links._PATHS for manager/tenant fallbacks",
                )

    def test_every_rail_viewname_resolves_on_full_urlconf(self):
        """Under default test URLconf, reverse or studio_resolve_url yields non-empty."""
        for vn in _STUDIO_RAIL_VIEWNAMES:
            with self.subTest(viewname=vn):
                try:
                    u = reverse(vn)
                except NoReverseMatch:
                    u = ""
                if not u:
                    u = studio_resolve_url(vn)
                self.assertTrue(
                    u,
                    f"{vn} must reverse() or resolve via deep_links",
                )
