"""The risk-digest narration must reach the AI gateway, not die on task-type lookup.

The pre-existing digest tests patch ``services.ai_helpers.invoke_with_request``,
which is the exact layer that resolves the task type — so they proved the
command handles a narrative, never that a narrative can be produced. These tests
patch one layer LOWER (``services.ai_gateway.invoke``) so the real task-type
resolution in ``ai_helpers`` runs.
"""

import uuid
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.analytics.models import RiskFactor
from apps.people.models import StudentProfile
from apps.schools.models import School


class NarrateRiskDigestTaskTypeTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:10]
        self.school = School.objects.create(
            name="Narrate School",
            slug=f"narrate-{uid}",
            subdomain=f"narrate-{uid}",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Dana",
            last_name="Test",
            student_code=f"sc-{uid}",
            admission_number=f"ad-{uid}",
        )
        RiskFactor.objects.create(
            school=self.school,
            student=self.student,
            score=85.0,
            reason_summary="heuristic",
        )

    def _run_with_patched_gateway(self, response):
        """Run the command with only the provider call stubbed out.

        Returns (stdout_text, list_of_task_types_the_gateway_saw).
        """
        seen: list[object] = []

        def _fake_invoke(task_type, prompt, **kwargs):
            seen.append(task_type)
            return response, {"provider": "test"}

        out = StringIO()
        with mock.patch("services.ai_gateway.invoke", side_effect=_fake_invoke):
            call_command(
                "ai_narrate_risk_digest",
                "--school", self.school.slug,
                "--top-n", "1",
                stdout=out,
            )
        return out.getvalue(), seen

    def test_task_type_resolves_and_the_gateway_is_actually_reached(self):
        text, seen = self._run_with_patched_gateway(
            "dana needs an attendance check-in today."
        )
        # Guard against the vacuous pass: if resolution failed, ai_helpers
        # returns None before the provider is ever contacted and `seen` is [].
        self.assertEqual(
            len(seen), 1,
            "the AI gateway was never invoked — the task type did not resolve",
        )
        from services.ai_gateway import TaskType

        self.assertIsInstance(seen[0], TaskType)
        self.assertIn("Narrative:", text)
        self.assertIn("attendance check-in", text)
        self.assertNotIn("Narrative unavailable", text)

    def test_declared_task_type_is_a_real_taskype_member(self):
        """The literal in the source must exist on the enum.

        ``invoke_with_request`` swallows an unknown name by returning None, so a
        typo here is invisible at runtime; assert on the value directly.
        """
        import ast
        import inspect

        from apps.analytics.management.commands import ai_narrate_risk_digest
        from services.ai_gateway import TaskType

        src = inspect.getsource(ai_narrate_risk_digest.Command._narrate)
        node = ast.parse(src.lstrip())
        declared = [
            kw.value
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            for kw in child.keywords
            if kw.arg == "task_type"
        ]
        self.assertEqual(len(declared), 1)
        value = declared[0]
        if isinstance(value, ast.Constant):
            name = value.value
            self.assertTrue(
                any(name in (m.value, m.name) for m in TaskType),
                f"task_type={name!r} is not a TaskType member",
            )
        else:
            # TaskType.X attribute form — resolve the attribute name.
            self.assertIsInstance(value, ast.Attribute)
            self.assertTrue(
                hasattr(TaskType, value.attr),
                f"TaskType has no member {value.attr!r}",
            )
