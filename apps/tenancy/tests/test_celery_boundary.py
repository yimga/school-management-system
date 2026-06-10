"""Celery tenant boundary decorator tests."""

from __future__ import annotations

import uuid

from django.test import SimpleTestCase

from apps.tenancy.boundary_core_guard import get_pinned_school_id
from apps.tenancy.celery_boundary import tenant_boundary_task


class CeleryBoundaryTests(SimpleTestCase):
    def test_tenant_boundary_task_pins_during_execution(self):
        school_id = str(uuid.uuid4())
        seen = []

        @tenant_boundary_task()
        def sample_task(school_id: str) -> None:
            seen.append(get_pinned_school_id())

        sample_task(school_id)
        self.assertEqual(seen, [school_id])
        self.assertIsNone(get_pinned_school_id())

    def test_tenant_boundary_task_unpinned_after_exception(self):
        school_id = str(uuid.uuid4())

        @tenant_boundary_task()
        def failing_task(school_id: str) -> None:
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            failing_task(school_id)
        self.assertIsNone(get_pinned_school_id())
