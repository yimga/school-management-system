"""Fast (no-DB) tests for the tenant agentic view's logic-bearing helpers.

These are the two parts of ``apps.portal.views_agentic`` that carry real risk:
- ``_normalize_params`` — the confirm-token security depends on it producing the
  SAME dict at propose-time (token issue) and confirm-time (token validate), so a
  user can't tamper with params between the two POSTs without invalidating the token.
- ``_role_permitted_actions`` — the role filter that decides which mutating actions
  a caller may even see/run.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.portal.views_agentic import _normalize_params, _role_permitted_actions
from services import ai_agentic_service as svc


def _spec(*params):
    return SimpleNamespace(parameters=tuple(params))


class NormalizeParamsTests(SimpleTestCase):
    def test_pulls_only_declared_params_stripped_and_nonempty(self):
        spec = _spec("student_id", "date", "reason")
        out = _normalize_params(spec, {"student_id": "  42 ", "date": "", "reason": "ill", "evil": "x"})
        self.assertEqual(out, {"student_id": "42", "reason": "ill"})
        # 'date' was empty -> dropped; 'evil' not declared -> ignored.
        self.assertNotIn("date", out)
        self.assertNotIn("evil", out)

    def test_deterministic_across_propose_and_confirm(self):
        # The token binds params_hash; propose-time and confirm-time normalization
        # of the same values MUST be identical (even with extra/ordering noise).
        spec = _spec("parent_id", "preferred_time")
        propose_src = {"parent_id": "9", "preferred_time": "2026-06-10T10:00"}
        confirm_src = {"preferred_time": "2026-06-10T10:00", "parent_id": "9", "csrfmiddlewaretoken": "abc"}
        self.assertEqual(_normalize_params(spec, propose_src), _normalize_params(spec, confirm_src))

    def test_missing_key_absent_not_blank(self):
        spec = _spec("a", "b")
        out = _normalize_params(spec, {"a": "1"})
        self.assertEqual(out, {"a": "1"})


class RolePermittedActionsTests(SimpleTestCase):
    def test_principal_gets_mark_only(self):
        names = {a.name for a in _role_permitted_actions(svc, ("PRINCIPAL",))}
        self.assertEqual(names, {"mark_student_absent"})  # callback needs COMMS_STAFF/ADMIN

    def test_leadership_gets_mark_only(self):
        names = {a.name for a in _role_permitted_actions(svc, ("LEADERSHIP",))}
        self.assertEqual(names, {"mark_student_absent"})

    def test_admin_gets_both(self):
        names = {a.name for a in _role_permitted_actions(svc, ("ADMIN",))}
        self.assertEqual(names, {"mark_student_absent", "schedule_parent_callback"})

    def test_unrelated_role_gets_nothing(self):
        names = {a.name for a in _role_permitted_actions(svc, ("STUDENT",))}
        self.assertEqual(names, set())
