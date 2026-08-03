"""Defense against blank sidebar pills: label-less nav items must never render.

A nav item with an empty label rendered as a blank cream pill in the v8 tenant
sidebar (bucketed into a spurious "Navigation" group) — seen live on the Gilead
tenant's backend Students page (inside the marketplace app sandbox). Injected /
config nav entries (``portal_sidebar_order``, the OS-nav registry, or a
marketplace app's contributed nav) can arrive without a label; the render path
must defend against that at BOTH the source dedupe and the template.

MUST-FIRE: each assertion fails on the pre-2026-08-03 code (the dedupe appended
label-less items and the template rendered ``{{ item.label }}`` with no guard).
"""

from __future__ import annotations

from pathlib import Path

from django.template.loader import get_template
from django.test import SimpleTestCase

from apps.siteconfig.portal_sidebar_items import _dedupe_sidebar_items


class DedupeDropsLabellessItemsTests(SimpleTestCase):
    """`_dedupe_sidebar_items` drops items with no visible label."""

    def test_empty_whitespace_and_none_labels_are_dropped(self):
        items = [
            {"id": "a", "label": "Students", "url": "/s/"},
            {"id": "b", "label": "", "url": "/blank/"},        # empty
            {"id": "c", "label": "   ", "url": "/ws/"},        # whitespace-only
            {"id": "d", "label": None, "url": "/none/"},       # None
            {"id": "e", "label": "Guardians", "url": "/g/"},
        ]
        out = _dedupe_sidebar_items(items)
        self.assertEqual([i["label"] for i in out], ["Students", "Guardians"])

    def test_labeled_items_survive_and_dedupe_still_works(self):
        items = [
            {"id": "a", "label": "Students", "url": "/s/"},
            {"id": "a2", "label": "Students", "url": "/s/"},   # dup label+url → dropped
            {"id": "b", "label": "Finance", "url": "/f/"},
        ]
        out = _dedupe_sidebar_items(items)
        self.assertEqual([i["id"] for i in out], ["a", "b"])


class V8SidebarTemplateLabelGuardSealTests(SimpleTestCase):
    """The v8 sidebar template must not render an item that has no label."""

    def test_item_render_guard_requires_label(self):
        origin = get_template("partials/portal_sidebar_v8_groups.html").origin.name
        src = Path(origin).read_text(encoding="utf-8")
        # The render guard requires a label, so a label-less item never renders
        # a blank pill even if one slips past the source dedupe.
        self.assertIn("item.url and item.label", src)
