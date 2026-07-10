"""Regression: /studio/automation/ 500 from a bad field name.

`get_automation_workflow_health_summary` did
``WorkflowPackAssignment.objects.filter(school=school).values_list("pack_id", ...)``
but the FK is ``workflow_pack`` (id accessor ``workflow_pack_id``); there is no
``pack_id`` field. Django resolves value-list field names eagerly inside the
``values_list()`` call, so this raised ``FieldError`` and 500'd the Automation
work-mode on every load. These are no-DB assertions — field resolution happens
against ``_meta`` before any query executes.
"""

from __future__ import annotations

from django.core.exceptions import FieldError
from django.test import SimpleTestCase

from apps.runtime_blueprints.models import WorkflowPackAssignment


class WorkflowPackAssignmentFieldNameTests(SimpleTestCase):
    def test_workflow_pack_id_resolves(self):
        # Must not raise — this is the field the summary query now uses.
        WorkflowPackAssignment.objects.none().values_list("workflow_pack_id", flat=True)

    def test_pack_id_is_not_a_field(self):
        # The exact shape that shipped the 500. If a future rename reintroduces a
        # ``pack_id`` field this test can be deleted; until then it locks the bug.
        with self.assertRaises(FieldError):
            WorkflowPackAssignment.objects.none().values_list("pack_id", flat=True)

    def test_workflow_pack_fk_exists(self):
        field = WorkflowPackAssignment._meta.get_field("workflow_pack")
        self.assertTrue(field.is_relation)
