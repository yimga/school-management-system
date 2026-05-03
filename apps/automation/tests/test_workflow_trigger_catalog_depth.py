"""Expanded trigger catalog depth (batch 1147+)."""

from django.test import TestCase

from apps.automation.workflow_trigger_catalog import (
    CLOSURE_SLICE_TRIGGER_KEYS,
    FULL_TRIGGER_CATALOG_KEYS,
    get_operator_trigger_catalog_for_school,
    sample_payload_for_trigger,
)
from apps.automation.workflow_graph_models import Workflow
from apps.schools.models import School


class WorkflowTriggerCatalogDepthTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Catalog School",
            slug="catalog-school",
            subdomain="catalog-school",
            is_active=True,
        )

    def test_full_catalog_eight_keys(self):
        self.assertEqual(len(FULL_TRIGGER_CATALOG_KEYS), 8)
        self.assertIn("offline_action_conflict", FULL_TRIGGER_CATALOG_KEYS)
        for key in FULL_TRIGGER_CATALOG_KEYS:
            self.assertIn(key, [c[0] for c in Workflow.Trigger.choices])

    def test_slice_vs_full_operator_rows(self):
        sid = str(self.school.pk)
        slice_rows = get_operator_trigger_catalog_for_school(sid, slice_only=True)
        full_rows = get_operator_trigger_catalog_for_school(sid, slice_only=False)
        self.assertEqual(len(slice_rows), len(CLOSURE_SLICE_TRIGGER_KEYS))
        self.assertEqual(len(full_rows), len(FULL_TRIGGER_CATALOG_KEYS))
        keys = {r["trigger_key"] for r in full_rows}
        self.assertEqual(keys, set(FULL_TRIGGER_CATALOG_KEYS))

    def test_each_trigger_sample_payload_schema(self):
        sid = str(self.school.pk)
        for key in FULL_TRIGGER_CATALOG_KEYS:
            payload = sample_payload_for_trigger(sid, key)
            self.assertIn("school_id", payload)
            self.assertEqual(payload["school_id"], sid)
