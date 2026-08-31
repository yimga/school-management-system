"""A model the viewer cannot VIEW must still get a catalog tile.

Reported 2026-08-30 and again 2026-08-31: the admin model catalog rendered
section headers with real counts -- "academic 32", "people 17" -- whose bodies
expanded to nothing, and the app-index rendered cards carrying only "+ Add"
with no label and no Changelist link.

``AdminSite._build_app_dict`` sets ``admin_url`` only when the viewer holds
``change`` or ``view`` on the model, and ``add_url`` only for ``add``. Both
catalog readers then did ``if not admin_url: continue``. For a viewer holding
add-without-view that dropped every row, which emptied the app, which emptied
the section -- so a permission shape silently deleted the catalog while the
counts computed elsewhere kept reporting the old totals.

Measured A/B on the real app list with ``admin_url`` stripped:

    OLD   sections=6  tiles=0     <- section headers, empty bodies
    NEW   sections=6  tiles=277

The tile is the navigation surface; a viewer who may add a record still needs
to find it. Only the LINK is conditional now, never the row.
"""

from __future__ import annotations

import unittest

from apps.siteconfig.platform_admin_catalog import (
    build_platform_admin_catalog,
    enrich_app_index_models,
)


def _app(app_label="people", *, admin_url, n=3):
    return {
        "app_label": app_label,
        "name": "People Management",
        "app_url": f"/admin/{app_label}/",
        "section": "people",
        "models": [
            {
                "name": f"Model {i}",
                "object_name": f"Model{i}",
                "admin_url": admin_url,
                "add_url": f"/admin/{app_label}/model{i}/add/",
            }
            for i in range(n)
        ],
    }


class CatalogKeepsUnviewableModelsTests(unittest.TestCase):
    def test_rows_without_admin_url_still_produce_tiles(self) -> None:
        catalog = build_platform_admin_catalog([_app(admin_url=None)])
        tiles = sum(len(a["models"]) for s in catalog["sections"] for a in s["apps"])
        self.assertEqual(
            tiles, 3, "an add-only viewer lost every tile in the section"
        )

    def test_the_section_survives_when_no_model_is_viewable(self) -> None:
        # The cascade that emptied the page: no model -> no app -> no section.
        catalog = build_platform_admin_catalog([_app(admin_url="")])
        self.assertEqual(catalog["section_count"], 1)
        self.assertEqual(catalog["sections"][0]["model_count"], 3)
        self.assertTrue(catalog["sections"][0]["apps"], "the app was dropped")

    def test_preview_models_are_populated_too(self) -> None:
        # The section card shows a preview strip; it reads from the same rows.
        catalog = build_platform_admin_catalog([_app(admin_url=None, n=8)])
        self.assertTrue(catalog["sections"][0]["preview_models"])

    def test_app_index_enrichment_keeps_unviewable_rows(self) -> None:
        rows = enrich_app_index_models(_app(admin_url=None))
        self.assertEqual(len(rows), 3, "app_index fell back to its bare branch")
        self.assertTrue(all(str(r.get("name") or "").strip() for r in rows))

    def test_rows_keep_their_name_and_add_url(self) -> None:
        # A tile with no label is not a tile. The add surface is the only place
        # such a viewer can go, so it must survive as well.
        rows = enrich_app_index_models(_app(admin_url=None))
        self.assertEqual(rows[0]["name"], "Model 0")
        self.assertTrue(rows[0]["add_url"])
        self.assertFalse(rows[0]["admin_url"], "admin_url should stay empty, not be invented")

    def test_viewable_rows_are_unchanged(self) -> None:
        # Back-compat: the permitted path must behave exactly as before.
        rows = enrich_app_index_models(_app(admin_url="/admin/people/model/"))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["admin_url"] for r in rows))

    def test_the_fixture_really_has_no_admin_url(self) -> None:
        # Every assertion above rests on this; a fixture that quietly carried an
        # admin_url would pass against the broken reader too.
        app = _app(admin_url=None)
        self.assertTrue(all(not m["admin_url"] for m in app["models"]))
        self.assertTrue(all(m["add_url"] for m in app["models"]))

    def test_hidden_models_are_still_excluded(self) -> None:
        # The one drop that IS correct must survive this change.
        app = _app(admin_url=None)
        app["models"][0]["hidden"] = True
        self.assertEqual(len(enrich_app_index_models(app)), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
