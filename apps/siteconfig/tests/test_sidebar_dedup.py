"""Sidebar nav de-duplication (no DB).

Locks the invariant that a nav rail never shows the same visible label twice —
the live defect where "Theme & Experience", "District & LMS interop", and
"Class Ranking" each rendered as consecutive double-rows because the same surface
was reachable via two route names (different id AND url, identical label).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.siteconfig.portal_sidebar_items import _dedupe_sidebar_items


class DedupeSidebarItemsTests(SimpleTestCase):
    def test_same_label_different_id_and_url_collapses(self):
        items = [
            {"id": "experience_studio", "label": "Theme & Experience", "url": "/school/studio/experience/"},
            {"id": "theme_hub", "label": "Theme & Experience", "url": "/siteconfig/theme-experience-hub/"},
        ]
        out = _dedupe_sidebar_items(items)
        self.assertEqual(len(out), 1)
        # First occurrence (canonical static entry) wins.
        self.assertEqual(out[0]["id"], "experience_studio")

    def test_same_id_collapses(self):
        items = [
            {"id": "class_ranking", "label": "Class Ranking", "url": "/a/"},
            {"id": "class_ranking", "label": "Class Ranking", "url": "/a/"},
        ]
        self.assertEqual(len(_dedupe_sidebar_items(items)), 1)

    def test_label_match_is_whitespace_and_case_insensitive(self):
        items = [
            {"id": "x", "label": "District & LMS interop", "url": "/x/"},
            {"id": "y", "label": "district &  lms  INTEROP", "url": "/y/"},
        ]
        self.assertEqual(len(_dedupe_sidebar_items(items)), 1)

    def test_distinct_labels_are_preserved(self):
        items = [
            {"id": "a", "label": "Class Ranking", "url": "/a/"},
            {"id": "b", "label": "School Ranking", "url": "/b/"},
            {"id": "c", "label": "Modules", "url": "/c/"},
        ]
        self.assertEqual(len(_dedupe_sidebar_items(items)), 3)

    def test_blank_labels_do_not_collapse_each_other(self):
        items = [
            {"id": "a", "label": "", "url": "/a/"},
            {"id": "b", "label": "", "url": "/b/"},
        ]
        # No id/label/url collision -> both survive (a divider-less rail is rare,
        # but an empty label must never be treated as a dedup key).
        self.assertEqual(len(_dedupe_sidebar_items(items)), 2)

    def test_order_is_stable(self):
        items = [
            {"id": "a", "label": "Alpha", "url": "/a/"},
            {"id": "b", "label": "Beta", "url": "/b/"},
            {"id": "a2", "label": "Alpha", "url": "/a2/"},
            {"id": "c", "label": "Gamma", "url": "/c/"},
        ]
        out = [x["label"] for x in _dedupe_sidebar_items(items)]
        self.assertEqual(out, ["Alpha", "Beta", "Gamma"])
