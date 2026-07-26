"""Communications lander resolves recipient/sender SCHOOL-SCOPED (no cross-school attach).

``communications_lander`` resolved the recipient (student/staff) and sender (staff)
with bare, school-unscoped ``StudentProfile.objects.filter(**{student_lookup: ...})``
/ ``TeacherProfile.objects.filter(**{staff_lookup: ...})`` lookups. On single-schema
(RLS / sqlite dev) deployments a same-external-id person from ANOTHER school resolves;
``Message.save()`` then derives ``Message.school`` from that recipient's primary
school, so the imported message lands under the WRONG tenant — invisible to the
correct one AND a cross-tenant leak. Recipient/sender resolution now routes through
the canonical school-scoping ``resolve_student`` helper, like every history /
assignment lander (commit 655e99447). The behavioural proof that ``resolve_student``
scopes by ``ctx.school`` lives in ``test_assignment_lander_student_scoping_2026_07_26``;
this pins that the communications lander actually uses it.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

from apps.migration_cloud.landers import _helpers

_LANDER = Path(_helpers.__file__).parent / "communications_lander.py"


class CommunicationsLanderScopingRegressionTests(SimpleTestCase):
    def test_communications_lander_routes_through_resolve_student(self):
        src = _LANDER.read_text(encoding="utf-8")
        self.assertIn(
            "resolve_student", src, "must use the school-scoped resolve_student helper"
        )
        # The bug pattern was a bare, school-unscoped profile lookup by external id.
        student_unscoped = re.compile(
            r"StudentProfile\.objects\.filter\(\s*\*\*\{\s*student_lookup"
        )
        staff_unscoped = re.compile(
            r"TeacherProfile\.objects\.filter\(\s*\*\*\{\s*staff_lookup"
        )
        self.assertIsNone(
            student_unscoped.search(src),
            "student recipient still resolved UNSCOPED via StudentProfile.objects.filter",
        )
        self.assertIsNone(
            staff_unscoped.search(src),
            "staff recipient/sender still resolved UNSCOPED via TeacherProfile.objects.filter",
        )
