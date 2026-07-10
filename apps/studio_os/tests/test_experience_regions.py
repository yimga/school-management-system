"""Canvas-first Experience builder — region catalog + scoped inspector (Phase 1).

No DB: pure catalog invariants + inspector builder. The critical invariant is
that every editable field a region declares is a real member of
THEME_EXPERIENCE_FIELD_NAMES (the publish-guarded theme SOT) — the builder must
never invent a parallel write path.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.studio_os.experience_regions import (
    FIELD_LABELS,
    STUDIO_EXPERIENCE_REGIONS,
    build_region_inspector,
    build_region_outline,
    build_role_filmstrip,
    region_keys,
    resolve_selected_region,
    resolve_view_mode,
    validate_region_catalog,
)


class RegionCatalogInvariantTests(SimpleTestCase):
    def test_catalog_has_six_regions(self):
        self.assertEqual(len(STUDIO_EXPERIENCE_REGIONS), 6)

    def test_validate_region_catalog_is_clean(self):
        # Every editable field ⊆ THEME_EXPERIENCE_FIELD_NAMES, keys unique, 1..N.
        self.assertEqual(validate_region_catalog(), [])

    def test_every_editable_field_is_in_theme_sot(self):
        from apps.siteconfig.forms import THEME_EXPERIENCE_FIELD_NAMES

        allowed = set(THEME_EXPERIENCE_FIELD_NAMES)
        for region in STUDIO_EXPERIENCE_REGIONS:
            for field_name in region["fields"]:
                self.assertIn(
                    field_name,
                    allowed,
                    msg=f"{region['key']}.{field_name} escaped the theme SOT",
                )

    def test_every_editable_field_has_a_label(self):
        for region in STUDIO_EXPERIENCE_REGIONS:
            for field_name in region["fields"]:
                self.assertIn(field_name, FIELD_LABELS)

    def test_region_keys_unique_and_ordered(self):
        keys = region_keys()
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(keys[0], "header")


class RegionResolutionTests(SimpleTestCase):
    def test_resolve_default_on_none(self):
        self.assertEqual(resolve_selected_region(None)["key"], "header")

    def test_resolve_default_on_unknown(self):
        self.assertEqual(resolve_selected_region("does-not-exist")["key"], "header")

    def test_resolve_known_region_case_insensitive(self):
        self.assertEqual(resolve_selected_region("HERO")["key"], "hero")

    def test_view_mode_normalization(self):
        self.assertEqual(resolve_view_mode("live"), "live")
        self.assertEqual(resolve_view_mode("LIVE"), "live")
        self.assertEqual(resolve_view_mode("draft"), "draft")
        self.assertEqual(resolve_view_mode(""), "draft")
        self.assertEqual(resolve_view_mode(None), "draft")
        self.assertEqual(resolve_view_mode("garbage"), "draft")


class RegionInspectorTests(SimpleTestCase):
    def _region(self, key):
        return resolve_selected_region(key)

    def test_first_row_is_selected_region(self):
        rows = build_region_inspector(self._region("header"), {})
        self.assertEqual(rows[0]["label"], "Selected region")
        self.assertEqual(rows[0]["value"], "Header and navigation")
        self.assertFalse(rows[0]["editable"])

    def test_last_row_is_publish_guard(self):
        rows = build_region_inspector(self._region("header"), {})
        self.assertEqual(rows[-1]["label"], "Publish guard")
        self.assertFalse(rows[-1]["editable"])

    def test_editable_rows_carry_field_anchor(self):
        rows = build_region_inspector(
            self._region("header"), {"primary_color": "#2fbcff"}
        )
        editable = [r for r in rows if r["editable"]]
        self.assertTrue(editable)
        primary = next(r for r in editable if r["field_name"] == "primary_color")
        self.assertEqual(primary["anchor"], "id_primary_color")
        self.assertEqual(primary["value"], "#2fbcff")
        self.assertEqual(primary["kind"], "color")
        self.assertEqual(primary["swatch"], "#2fbcff")

    def test_missing_value_renders_not_set(self):
        rows = build_region_inspector(self._region("header"), {})
        primary = next(
            r for r in rows if r.get("field_name") == "primary_color"
        )
        self.assertEqual(primary["value"], "Not set")
        self.assertEqual(primary["swatch"], "")

    def test_bool_values_render_on_off(self):
        rows = build_region_inspector(
            self._region("mobile"), {"use_dark_mode": True}
        )
        dark = next(r for r in rows if r.get("field_name") == "use_dark_mode")
        self.assertEqual(dark["value"], "On")

    def test_derived_rows_are_read_only(self):
        rows = build_region_inspector(self._region("header"), {})
        derived = [r for r in rows if r["kind"] == "derived"]
        self.assertTrue(derived)
        self.assertTrue(all(not r["editable"] for r in derived))


class RegionOutlineTests(SimpleTestCase):
    def test_outline_marks_active(self):
        outline = build_region_outline("cards")
        active = [r for r in outline if r["active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["key"], "cards")

    def test_outline_default_active_is_first(self):
        outline = build_region_outline(None)
        self.assertTrue(outline[0]["active"])
        self.assertEqual(outline[0]["key"], "header")


class RoleFilmstripTests(SimpleTestCase):
    def test_empty_entries(self):
        self.assertEqual(build_role_filmstrip([]), [])
        self.assertEqual(build_role_filmstrip(None), [])

    def test_descriptor_mapping(self):
        entries = [
            {"role": "admin", "label": "Admin shell", "url": "/a/"},
            {"role": "teacher", "label": "Teacher dashboard", "url": "/t/"},
            {"role": "parent", "label": "Parent portal", "url": "/p/"},
            {"role": "student", "label": "Student portal", "url": "/s/"},
            {"role": "finance", "label": "Finance console", "url": "/f/"},
        ]
        strip = build_role_filmstrip(entries)
        got = {t["label"]: t["descriptor"] for t in strip}
        self.assertEqual(got["Admin shell"], "Backend density")
        self.assertEqual(got["Teacher dashboard"], "Primary preview")
        self.assertEqual(got["Parent portal"], "Family surface")
        self.assertEqual(got["Student portal"], "Mobile first")
        self.assertEqual(got["Finance console"], "Table clarity")

    def test_entries_without_url_are_dropped(self):
        entries = [
            {"role": "teacher", "label": "Teacher", "url": ""},
            {"role": "parent", "label": "Parent", "url": "#"},
            {"role": "admin", "label": "Admin", "url": "/a/"},
        ]
        strip = build_role_filmstrip(entries)
        self.assertEqual(len(strip), 1)
        self.assertEqual(strip[0]["label"], "Admin")

    def test_unknown_role_gets_default_descriptor(self):
        strip = build_role_filmstrip([{"role": "librarian", "label": "Library", "url": "/l/"}])
        self.assertEqual(strip[0]["descriptor"], "Role preview")

    def test_limit_is_respected(self):
        entries = [
            {"role": "teacher", "label": f"T{i}", "url": f"/t/{i}/"} for i in range(10)
        ]
        self.assertEqual(len(build_role_filmstrip(entries, limit=5)), 5)

    def test_non_dict_entries_skipped(self):
        strip = build_role_filmstrip([None, "x", {"role": "teacher", "label": "T", "url": "/t/"}])
        self.assertEqual(len(strip), 1)
