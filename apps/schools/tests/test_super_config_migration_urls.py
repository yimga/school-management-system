"""
Final verification: all Admin→Super migration URLs resolve and return 200 (no 500).
RUNBOOK_ADMIN_TO_SUPER_MIGRATION final checklist. Requires superuser on manager host.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.super_admin_bridge_registry import (
    PLATFORM_ADMIN_BRIDGE_ORDER,
    PLATFORM_ADMIN_BRIDGES,
)


def _admin_changelist_path_tail(admin_url_name: str) -> str:
    """Last path segment of reversed admin changelist URL — must appear in 302 Location."""
    loc = reverse(str(admin_url_name)).lower()
    parts = [p for p in loc.split("/") if p]
    return parts[-1] if parts else ""


@override_settings(ALLOWED_HOSTS=["*"])
class SuperConfigMigrationUrlTests(TestCase):
    """Verify every new super config URL returns 200 for superuser on manager host."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="super_verify",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.host = "manager.runmycampus.com"

    def _get(self, url_name, args=None, kwargs=None, query=None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        url = reverse(url_name, args=args, kwargs=kwargs)
        if query:
            url = f"{url}?{query}"
        return self.client.get(url, HTTP_HOST=self.host)

    def test_config_hub_redirects_to_system_config(self):
        response = self._get("super:config_hub")
        self.assertIn(
            response.status_code, (200, 302), "Config hub must redirect or render"
        )
        if response.status_code == 302:
            self.assertIn(
                "console/",
                response.get("Location", ""),
                "Config hub must redirect to System config",
            )
            follow = self.client.get(response["Location"], HTTP_HOST=self.host)
            self.assertEqual(follow.status_code, 200, "System config must return 200")
        else:
            self.assertEqual(response.status_code, 200)

    def test_site_settings_list_200(self):
        response = self._get("super:site_settings_list")
        self.assertEqual(
            response.status_code, 200, "Site settings list must return 200"
        )

    def test_regions_list_200(self):
        response = self._get("super:regions_list")
        self.assertEqual(response.status_code, 200, "Regions list must return 200")

    def test_grading_list_200(self):
        response = self._get("super:grading_list")
        self.assertEqual(response.status_code, 200, "Grading list must return 200")

    def test_plans_list_200(self):
        response = self._get("super:plans_list")
        self.assertEqual(response.status_code, 200, "Plans list must return 200")

    def test_feature_toggles_list_200(self):
        response = self._get("super:feature_toggles_list")
        self.assertEqual(
            response.status_code, 200, "Feature toggles list must return 200"
        )

    def test_schools_list_200(self):
        response = self._get("super:schools_list")
        self.assertEqual(response.status_code, 200, "Schools list must return 200")

    def test_schools_list_pagination_and_filters(self):
        response = self._get(
            "super:schools_list", query="page=1&is_active=1&q=test&country_code=US"
        )
        self.assertEqual(
            response.status_code, 200, "Schools list with filters must return 200"
        )

    def test_site_settings_edit_200_or_404(self):
        # Edit requires existing pk; 404 if no SiteSettings
        from apps.siteconfig.models import SiteSettings

        first = SiteSettings.objects.first()
        if first:
            response = self._get("super:site_settings_edit", kwargs={"pk": first.pk})
            self.assertEqual(
                response.status_code,
                200,
                "Site settings edit must return 200 when pk exists",
            )
        else:
            response = self._get("super:site_settings_edit", kwargs={"pk": 1})
            self.assertEqual(
                response.status_code,
                404,
                "Site settings edit must return 404 when pk missing",
            )

    def test_ai_model_hub_200(self):
        response = self._get("super:ai_model_hub")
        self.assertEqual(response.status_code, 200, "AI model hub must return 200")

    def test_incidents_list_200(self):
        response = self._get("super:incidents_list")
        self.assertEqual(response.status_code, 200, "Incidents list must return 200")

    def test_billing_accounts_list_200(self):
        response = self._get("super:billing_accounts_list")
        self.assertEqual(
            response.status_code, 200, "Billing accounts list must return 200"
        )

    def test_migration_runs_list_200(self):
        response = self._get("super:migration_runs_list")
        self.assertEqual(
            response.status_code, 200, "Migration runs list must return 200"
        )

    def test_platform_operator_hub_200(self):
        response = self._get("super:platform_operator_hub")
        self.assertEqual(
            response.status_code,
            200,
            "Platform operator hub must return 200",
        )
        self.assertIn(
            b"changelist",
            response.content.lower(),
            "Hub must render advanced model registry section",
        )

    def test_admin_bridge_redirects_to_platform_changelists(self):
        for bridge_key in PLATFORM_ADMIN_BRIDGE_ORDER:
            with self.subTest(bridge_key=bridge_key):
                r = self._get("super:admin_bridge", kwargs={"bridge_key": bridge_key})
                self.assertEqual(r.status_code, 302, bridge_key)
                admin_url = PLATFORM_ADMIN_BRIDGES[bridge_key]["admin_url"]
                needle = _admin_changelist_path_tail(str(admin_url))
                self.assertIn(
                    needle,
                    r.get("Location", "").lower(),
                    msg=f"admin bridge {bridge_key}",
                )

    def test_platform_admin_bridge_registry_order_matches_bridges(self):
        """ORDER and BRIDGES must list the same keys (single source for hub + redirects)."""
        self.assertEqual(
            len(PLATFORM_ADMIN_BRIDGE_ORDER),
            len(set(PLATFORM_ADMIN_BRIDGE_ORDER)),
            "PLATFORM_ADMIN_BRIDGE_ORDER must not contain duplicates",
        )
        self.assertEqual(
            set(PLATFORM_ADMIN_BRIDGE_ORDER),
            set(PLATFORM_ADMIN_BRIDGES.keys()),
            "ORDER and PLATFORM_ADMIN_BRIDGES keys must match exactly",
        )

    def test_admin_bridge_unknown_key_404(self):
        r = self._get("super:admin_bridge", kwargs={"bridge_key": "no-such-bridge"})
        self.assertEqual(r.status_code, 404)

    def test_legacy_admin_bridge_named_urls_match_canonical_target(self):
        """Old ``super:admin_bridge_*`` names still resolve; same 302 target as slug route."""
        legacy_pairs = (
            ("super:admin_bridge_integrations", "integrations"),
            ("super:admin_bridge_marketplace_apps", "marketplace_apps"),
            ("super:admin_bridge_packages_installed", "packages_installed"),
            ("super:admin_bridge_experience_packs", "experience_packs"),
            ("super:admin_bridge_runtime_defaults", "runtime_defaults"),
            ("super:admin_bridge_ai_model_registry", "ai_model_registry"),
            ("super:admin_bridge_global_brand_registry", "global_brand_registry"),
        )
        for url_name, bridge_key in legacy_pairs:
            with self.subTest(url_name=url_name):
                legacy = self._get(url_name)
                canonical = self._get(
                    "super:admin_bridge", kwargs={"bridge_key": bridge_key}
                )
                self.assertEqual(legacy.status_code, 302, url_name)
                self.assertEqual(canonical.status_code, 302, bridge_key)
                self.assertEqual(
                    legacy.get("Location", ""),
                    canonical.get("Location", ""),
                    msg=f"{url_name} vs canonical {bridge_key}",
                )

    def test_super_config_crud_forms_get_200(self):
        """Platform catalog CRUD in super (not platform /admin/)."""
        self.assertEqual(self._get("super:region_add").status_code, 200)
        self.assertEqual(self._get("super:grading_add").status_code, 200)
        self.assertEqual(
            self._get("super:grading_add", query="region=CMR").status_code, 200
        )
        self.assertEqual(self._get("super:plan_add").status_code, 200)
        self.assertEqual(self._get("super:plan_addon_add").status_code, 200)
        self.assertEqual(self._get("super:feature_toggle_add").status_code, 200)

        from apps.global_registries.models import RegionConfig as GRRegion
        from apps.global_registries.models import GradingScaleConfig
        from apps.plans_entitlements.models import Plan, PlanAddon
        from apps.policies_rules.models import FeatureToggleDefinition

        r = GRRegion.objects.first()
        if r:
            self.assertEqual(
                self._get("super:region_edit", kwargs={"code": r.code}).status_code,
                200,
            )
        else:
            self.assertEqual(
                self._get("super:region_edit", kwargs={"code": "__none__"}).status_code,
                404,
            )

        g = GradingScaleConfig.objects.first()
        if g:
            self.assertEqual(
                self._get("super:grading_edit", kwargs={"pk": g.pk}).status_code, 200
            )
        else:
            self.assertEqual(
                self._get("super:grading_edit", kwargs={"pk": 999999}).status_code,
                404,
            )

        p = Plan.objects.first()
        if p:
            self.assertEqual(
                self._get("super:plan_edit", kwargs={"pk": p.pk}).status_code, 200
            )
        else:
            self.assertEqual(
                self._get("super:plan_edit", kwargs={"pk": 999999}).status_code, 404
            )

        a = PlanAddon.objects.first()
        if a:
            self.assertEqual(
                self._get("super:plan_addon_edit", kwargs={"pk": a.pk}).status_code,
                200,
            )
        else:
            self.assertEqual(
                self._get("super:plan_addon_edit", kwargs={"pk": 999999}).status_code,
                404,
            )

        f = FeatureToggleDefinition.objects.first()
        if f:
            self.assertEqual(
                self._get(
                    "super:feature_toggle_edit", kwargs={"pk": f.pk}
                ).status_code,
                200,
            )
        else:
            self.assertEqual(
                self._get(
                    "super:feature_toggle_edit", kwargs={"pk": 999999}
                ).status_code,
                404,
            )

    def test_country_multipliers_super_200(self):
        self.assertEqual(
            self._get("super:country_multipliers_list").status_code, 200
        )
        self.assertEqual(self._get("super:country_multiplier_add").status_code, 200)
        from apps.plans_entitlements.models import CountryMultiplier

        m = CountryMultiplier.objects.first()
        if m:
            self.assertEqual(
                self._get(
                    "super:country_multiplier_edit", kwargs={"pk": m.pk}
                ).status_code,
                200,
            )
            self.assertEqual(
                self._get(
                    "super:country_multiplier_delete", kwargs={"pk": m.pk}
                ).status_code,
                200,
            )
        else:
            self.assertEqual(
                self._get(
                    "super:country_multiplier_edit", kwargs={"pk": 999999}
                ).status_code,
                404,
            )
            self.assertEqual(
                self._get(
                    "super:country_multiplier_delete", kwargs={"pk": 999999}
                ).status_code,
                404,
            )

    def test_catalog_delete_confirm_get_200_or_404(self):
        """Delete flows: confirmation page (GET) resolves like edit."""
        from apps.global_registries.models import RegionConfig as GRRegion
        from apps.global_registries.models import GradingScaleConfig
        from apps.plans_entitlements.models import Plan, PlanAddon
        from apps.policies_rules.models import FeatureToggleDefinition

        r = GRRegion.objects.first()
        if r:
            self.assertEqual(
                self._get("super:region_delete", kwargs={"code": r.code}).status_code,
                200,
            )
        else:
            self.assertEqual(
                self._get(
                    "super:region_delete", kwargs={"code": "__x__"}
                ).status_code,
                404,
            )

        g = GradingScaleConfig.objects.first()
        if g:
            self.assertEqual(
                self._get("super:grading_delete", kwargs={"pk": g.pk}).status_code,
                200,
            )
        else:
            self.assertEqual(
                self._get("super:grading_delete", kwargs={"pk": 999999}).status_code,
                404,
            )

        p = Plan.objects.first()
        if p:
            self.assertEqual(
                self._get("super:plan_delete", kwargs={"pk": p.pk}).status_code, 200
            )
        else:
            self.assertEqual(
                self._get("super:plan_delete", kwargs={"pk": 999999}).status_code, 404
            )

        a = PlanAddon.objects.first()
        if a:
            self.assertEqual(
                self._get("super:plan_addon_delete", kwargs={"pk": a.pk}).status_code,
                200,
            )
        else:
            self.assertEqual(
                self._get("super:plan_addon_delete", kwargs={"pk": 999999}).status_code,
                404,
            )

        f = FeatureToggleDefinition.objects.first()
        if f:
            self.assertEqual(
                self._get(
                    "super:feature_toggle_delete", kwargs={"pk": f.pk}
                ).status_code,
                200,
            )
        else:
            self.assertEqual(
                self._get(
                    "super:feature_toggle_delete", kwargs={"pk": 999999}
                ).status_code,
                404,
            )
