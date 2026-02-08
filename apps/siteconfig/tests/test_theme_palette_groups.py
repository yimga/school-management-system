from dataclasses import dataclass

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.siteconfig.models import ThemePack
from apps.siteconfig.theme_palette_groups import THEME_PALETTE_GROUPS, build_theme_pack_groups


@dataclass(frozen=True)
class _Pack:
    slug: str
    name: str


class ThemePaletteGroupingTests(SimpleTestCase):
    def test_known_slugs_are_grouped_and_unknown_slugs_go_to_other(self):
        packs = [
            _Pack(slug="admin-campus-blue", name="Campus Blue"),
            _Pack(slug="custom-school-pack", name="Custom School Pack"),
        ]

        groups = build_theme_pack_groups(
            packs,
            groups=(
                ("Blues", ("admin-campus-blue",)),
                ("Warm", ("admin-sunset-study",)),
            ),
        )

        self.assertEqual(groups[0][0], "Blues")
        self.assertEqual([p.slug for p in groups[0][1]], ["admin-campus-blue"])
        self.assertEqual(groups[-1][0], "Other")
        self.assertEqual([p.slug for p in groups[-1][1]], ["custom-school-pack"])

    def test_empty_input_returns_no_groups(self):
        self.assertEqual(build_theme_pack_groups([], groups=(("Blues", ("admin-campus-blue",)),)), [])

    def test_canonical_groups_cover_curated_admin_catalog(self):
        slugs = [slug for _label, group_slugs in THEME_PALETTE_GROUPS for slug in group_slugs]
        self.assertEqual(len(slugs), 18)
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertIn("admin-academic-slate", slugs)
        self.assertIn("admin-midnight-scholar", slugs)
        self.assertIn("admin-high-contrast-accessible", slugs)


class ThemePaletteSeedCommandTests(TestCase):
    def test_seed_command_builds_curated_24_pack_catalog(self):
        call_command("seed_admin_dashboard_palettes", reset=True)
        curated = ThemePack.objects.filter(
            slug__in=[
                "admin-academic-slate",
                "admin-academic-authority",
                "admin-campus-blue",
                "admin-ocean-blue",
                "admin-indigo-lecture",
                "admin-digital-lavender",
                "admin-gilead-warm-pink",
                "admin-sunset-study",
                "admin-sunset-warm",
                "admin-forest-academy",
                "admin-modern-sage",
                "admin-verdant-growth",
                "admin-tech-pioneer",
                "admin-cyber-lab",
                "admin-glassmorphism",
                "admin-high-contrast-accessible",
                "admin-conservatory",
                "admin-midnight-scholar",
                "portal-active-learner",
                "portal-creative-spark",
                "portal-sunset-scholar",
                "portal-grounded-mentor",
                "portal-playroom",
                "portal-orchard",
            ]
        )
        self.assertEqual(curated.count(), 24)
        self.assertEqual(curated.filter(applies_to_admin=True).count(), 18)
