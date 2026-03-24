"""
Wedge 1–6 world-class: verify all shipped items are implemented (not backlog/deferred).

- Four wedge URLs reverse and return acceptable status (200 or 302).
- AUS and NZL in REGIONAL_POLICY_PACKS and get_regional_policy_pack.
- Trust center template includes Data residency, Resilience & BCP, District & ERP cards.
- Nav includes Curriculum & region packs and One SIS, any LMS.
"""

from pathlib import Path

from django.test import Client, TestCase, override_settings
from django.urls import reverse


ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"


# Wedge world-class URLs (manager urlconf) — must resolve and return 200 (logged in) or 302 (login redirect)
WEDGE_PATHS = [
    ("super:curriculum_packs", "/super/curriculum-packs/"),
    ("super:one_sis_any_lms", "/super/one-sis-any-lms/"),
    ("super:advancement_hub", "/super/advancement/"),
    ("super:he_pack", "/super/he-pack/"),
    ("super:education_systems", "/super/education-systems/"),  # Wedges 14–22
    ("super:learning_delivery_packs", "/super/learning-delivery-packs/"),  # Phase J
    ("super:district_enterprise", "/super/district-enterprise/"),
    ("super:wedge_index", "/super/wedge/"),
    ("super:native_roster_connectors", "/super/native-roster-connectors/"),
]


@override_settings(ALLOWED_HOSTS=["*"])
class WedgeWorldClassImplementedTests(TestCase):
    """Validate wedge world-class implementation is done (not deferred)."""

    def test_wedge_urls_reverse(self):
        """All four wedge URL names must reverse under manager urlconf."""
        with self.settings(ROOT_URLCONF="config.manager_urls"):
            for name, expected_path in WEDGE_PATHS:
                with self.subTest(url_name=name):
                    url = reverse(name)
                    self.assertTrue(
                        url.endswith(expected_path.rstrip("/"))
                        or expected_path.rstrip("/") in url,
                        f"{name} reversed to {url}, expected path like {expected_path}",
                    )

    def test_wedge_paths_acceptable_status(self):
        """GET wedge paths must not return 404 or 500 (200 or 302 allowed)."""
        client = Client()
        with self.settings(ROOT_URLCONF="config.manager_urls"):
            for _name, path in WEDGE_PATHS:
                with self.subTest(path=path):
                    response = client.get(path, follow=False)
                    self.assertIn(
                        response.status_code,
                        (200, 302),
                        f"GET {path} returned {response.status_code}; expected 200 or 302",
                    )

    def test_aus_nzl_in_regional_policy_packs(self):
        """AUS and NZL must be in REGIONAL_POLICY_PACKS and resolvable via get_regional_policy_pack."""
        from apps.siteconfig.tenant_config import (
            REGIONAL_POLICY_PACKS,
            get_regional_policy_pack,
        )

        self.assertIn(
            "AUS", REGIONAL_POLICY_PACKS, "AUS must be in REGIONAL_POLICY_PACKS"
        )
        self.assertIn(
            "NZL", REGIONAL_POLICY_PACKS, "NZL must be in REGIONAL_POLICY_PACKS"
        )
        aus = get_regional_policy_pack("AUS")
        self.assertTrue(aus, "get_regional_policy_pack('AUS') must return non-empty")
        nzl = get_regional_policy_pack("NZL")
        self.assertTrue(nzl, "get_regional_policy_pack('NZL') must return non-empty")
        self.assertEqual(aus.get("code"), "AUS")
        self.assertEqual(nzl.get("code"), "NZL")

    def test_trust_center_has_world_class_cards(self):
        """Trust center template must include Data residency, Resilience & BCP, District & ERP."""
        trust_path = TEMPLATES / "schools" / "super_trust_center.html"
        self.assertTrue(trust_path.exists(), "super_trust_center.html must exist")
        text = trust_path.read_text(encoding="utf-8", errors="replace")
        self.assertIn(
            "Data residency", text, "Trust center must have Data residency card"
        )
        self.assertIn(
            "Resilience", text, "Trust center must have Resilience & BCP card"
        )
        self.assertIn("District", text, "Trust center must have District & ERP card")

    def test_wedge_templates_exist(self):
        """All four wedge page templates must exist."""
        for name, _path in WEDGE_PATHS:
            if name == "super:curriculum_packs":
                path = TEMPLATES / "schools" / "super_curriculum_packs.html"
            elif name == "super:one_sis_any_lms":
                path = TEMPLATES / "schools" / "super_one_sis_any_lms.html"
            elif name == "super:advancement_hub":
                path = TEMPLATES / "schools" / "super_advancement_hub.html"
            elif name == "super:he_pack":
                path = TEMPLATES / "schools" / "super_he_pack.html"
            elif name == "super:education_systems":
                path = TEMPLATES / "schools" / "super_education_systems.html"
            else:
                continue
            with self.subTest(template=path.name):
                self.assertTrue(path.exists(), f"{path} must exist")
        # Phase 2 advancement placeholder
        phase2 = TEMPLATES / "schools" / "super_advancement_phase2_placeholder.html"
        self.assertTrue(
            phase2.exists(), "super_advancement_phase2_placeholder.html must exist"
        )
        # Geography (Wedges 7–13)
        geo = TEMPLATES / "schools" / "super_geography.html"
        self.assertTrue(geo.exists(), "super_geography.html must exist")
        dist_ent = TEMPLATES / "schools" / "super_district_enterprise.html"
        self.assertTrue(dist_ent.exists(), "super_district_enterprise.html must exist")
        for tname in (
            "super_wedge_index.html",
            "super_wedge_operator_detail.html",
            "super_native_roster_connectors.html",
        ):
            p = TEMPLATES / "schools" / tname
            self.assertTrue(p.exists(), f"{p} must exist")

    def test_geography_packs_resolve(self):
        """Wedges 7–13: WAEC, AFR_FR, ASIA, CAN, LATAM_ES, MENA must resolve via get_regional_policy_pack."""
        from apps.siteconfig.tenant_config import get_regional_policy_pack

        for code in ("WAEC", "AFR_FR", "ASIA", "CAN", "LATAM_ES", "MENA"):
            with self.subTest(pack=code):
                pack = get_regional_policy_pack(code)
                self.assertTrue(
                    pack, f"get_regional_policy_pack('{code}') must return non-empty"
                )
                self.assertEqual(pack.get("code"), code)

    def test_moe_presets_geography_world_class(self):
        """World-class Geography: moe_presets include asia_generic, canada_provincial, latam_es, mena_generic."""
        from apps.reports.moe_presets import get_moe_preset

        for preset_id in (
            "asia_generic",
            "canada_provincial",
            "latam_es",
            "mena_generic",
        ):
            with self.subTest(preset=preset_id):
                preset = get_moe_preset(preset_id)
                self.assertTrue(
                    preset, f"get_moe_preset('{preset_id}') must return non-empty"
                )
                self.assertIn("name", preset)
                self.assertIn("description", preset)

    def test_education_systems_14_22_world_class(self):
        """Wedges 14–22: static sector tuple + super surface (DB rows: validate_wedges_14_22.py)."""
        from apps.registries.services import WEDGE_14_22_SECTOR_CODES

        self.assertEqual(len(WEDGE_14_22_SECTOR_CODES), 9)
        self.assertEqual(WEDGE_14_22_SECTOR_CODES[-2:], ("NGO", "MULTI_CAMPUS"))
        with self.settings(ROOT_URLCONF="config.manager_urls"):
            url = reverse("super:education_systems")
            self.assertIn("/education-systems", url)
        self.assertTrue(
            (TEMPLATES / "schools" / "super_education_systems.html").exists()
        )
