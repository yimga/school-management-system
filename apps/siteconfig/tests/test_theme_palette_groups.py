from dataclasses import dataclass

from django.test import SimpleTestCase

from apps.siteconfig.theme_palette_groups import build_theme_pack_groups


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
