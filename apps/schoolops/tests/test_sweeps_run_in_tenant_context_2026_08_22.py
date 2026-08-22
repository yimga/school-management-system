"""The daily schoolops sweeps must run inside each school's tenant context.

``apps.schoolops`` is in TENANT_APPS only (config/settings.py), so under
``USE_DJANGO_TENANTS`` its tables exist EXCLUSIVELY inside tenant schemas. Both
daily sweeps were plain ``@shared_task``s with no tenant wrapper, and the worker
that runs them (``celery -A config worker``) has no tenant middleware -- its
connection sits on ``public``. The query therefore hit a schema where the
relation does not exist, raised ProgrammingError, and was swallowed by each
task's own ``except Exception`` into ``errors += 1``. Every night, forever, a
clean-looking zero-work run.

The same hole sat on the enqueue side: the sweep handed a bare row pk to
``.delay()``, and the worker picking that message up had no context either.

These tests do not need Postgres to prove it. Under SQLite there is one schema,
so a missing wrapper does not raise -- what they assert instead is the STRUCTURE
that makes the wrapper real:

  * every school is visited, each inside ``_run_with_tenant_context``;
  * the id handed to the point-shot task is accompanied by its ``school_id``;
  * one school's sweep cannot see another school's rows;
  * a tenant that fails to resolve is counted, not fatal.
"""

import uuid
from unittest.mock import patch

from django.test import TestCase

from apps.schoolops.models import InventoryItem
from apps.schoolops.tasks import (
    sweep_low_inventory_stock,
    sweep_low_meal_plan_balances,
)
from apps.schools.models import School


def _school(tag):
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}", slug=slug, subdomain=slug, is_active=True
    )


class SweepTenantContextTests(TestCase):
    def setUp(self):
        self.a = _school("swp-a")
        self.b = _school("swp-b")
        self.item_a = InventoryItem.objects.create(
            school=self.a, name="Chalk A", quantity=1, reorder_threshold=10
        )
        self.item_b = InventoryItem.objects.create(
            school=self.b, name="Chalk B", quantity=1, reorder_threshold=10
        )
        # Creating an already-low row fires the post_save signal, which stamps
        # last_low_stock_notified_at. The sweep exists precisely to catch rows the
        # SIGNAL MISSED, so it skips anything stamped -- clear it, via .update()
        # so the signal does not simply re-stamp.
        InventoryItem.objects.filter(
            pk__in=[self.item_a.pk, self.item_b.pk]
        ).update(last_low_stock_notified_at=None)
        self.item_a.refresh_from_db()
        self.item_b.refresh_from_db()
        self.assertIsNone(self.item_a.last_low_stock_notified_at)
        self.assertIsNone(self.item_b.last_low_stock_notified_at)

    def test_inventory_sweep_enters_tenant_context_for_every_school(self):
        seen = []
        real = None

        def _record(*, school_id, runnable, **kw):
            seen.append(str(school_id))
            return runnable()

        with patch(
            "apps.schools.celery_tasks._run_with_tenant_context", side_effect=_record
        ):
            summary = sweep_low_inventory_stock()

        self.assertIn(str(self.a.pk), seen)
        self.assertIn(str(self.b.pk), seen)
        self.assertGreaterEqual(summary["schools"], 2)
        self.assertEqual(summary["schools_failed"], 0)
        self.assertIsNone(real)

    def test_inventory_sweep_scoped_to_one_school_ignores_the_other(self):
        summary = sweep_low_inventory_stock(school_id=str(self.a.pk))
        self.assertEqual(summary["schools"], 1)
        self.assertEqual(
            summary["scanned"],
            1,
            "a single-school sweep must not scan another school's items",
        )
        self.item_a.refresh_from_db()
        self.item_b.refresh_from_db()
        self.assertIsNotNone(self.item_a.last_low_stock_notified_at)
        self.assertIsNone(
            self.item_b.last_low_stock_notified_at,
            "school B was never swept; its item must be untouched",
        )

    def test_inventory_point_shot_is_enqueued_with_its_school_id(self):
        calls = []
        with patch(
            "apps.schoolops.tasks.notify_low_inventory_stock.delay",
            side_effect=lambda **kw: calls.append(kw),
        ):
            sweep_low_inventory_stock(school_id=str(self.a.pk))

        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(calls[0]["inventory_item_id"], self.item_a.pk)
        self.assertEqual(
            calls[0].get("school_id"),
            str(self.a.pk),
            "the worker has no tenant context; the row pk alone cannot find the row",
        )

    def test_one_unresolvable_tenant_does_not_end_the_sweep(self):
        def _boom(*, school_id, runnable, **kw):
            if str(school_id) == str(self.a.pk):
                raise ValueError("Tenant client could not be resolved")
            return runnable()

        with patch(
            "apps.schools.celery_tasks._run_with_tenant_context", side_effect=_boom
        ):
            summary = sweep_low_inventory_stock()

        self.assertEqual(summary["schools_failed"], 1)
        self.assertGreaterEqual(summary["errors"], 1)
        self.assertGreaterEqual(
            summary["schools"], 2, "the sweep must continue past a bad tenant"
        )
        self.item_b.refresh_from_db()
        self.assertIsNotNone(
            self.item_b.last_low_stock_notified_at,
            "school B follows A in the loop and must still be swept",
        )

    def test_meal_plan_sweep_enters_tenant_context_for_every_school(self):
        seen = []

        def _record(*, school_id, runnable, **kw):
            seen.append(str(school_id))
            return runnable()

        with patch(
            "apps.schools.celery_tasks._run_with_tenant_context", side_effect=_record
        ):
            summary = sweep_low_meal_plan_balances()

        self.assertIn(str(self.a.pk), seen)
        self.assertIn(str(self.b.pk), seen)
        self.assertGreaterEqual(summary["schools"], 2)
        self.assertEqual(summary["schools_failed"], 0)
