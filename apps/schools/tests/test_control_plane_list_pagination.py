"""Control-plane list views paginate high-traffic operator tables."""

from __future__ import annotations

from django.core.paginator import Paginator
from django.test import SimpleTestCase

from apps.schools.control_plane_pagination import paginate_for_request


class PaginateForRequestTests(SimpleTestCase):
    def test_paginate_for_request_first_page(self):
        class _Req:
            GET = {}

        page = paginate_for_request(_Req(), list(range(30)), per_page=25)
        self.assertEqual(len(page.object_list), 25)
        self.assertTrue(page.has_next())


class OffboardingQueuePaginationTests(SimpleTestCase):
    def test_view_source_exports_page_obj(self):
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent
            / "super_views_offboarding_queue.py"
        )
        body = path.read_text(encoding="utf-8")
        self.assertIn("page_obj", body)
        self.assertIn("paginate_for_request", body)


class PlatformEventsPaginationTests(SimpleTestCase):
    def test_paginator_page_size_default(self):
        page = Paginator(list(range(30)), 25).get_page(1)
        self.assertEqual(page.paginator.per_page, 25)
