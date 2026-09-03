"""Agent Q, 2026-09-01 -- a OneRoster class write keeps THIS school's classCode.

``_upsert_class`` used to decide the stored ``Classroom.code`` with a GLOBAL
existence check::

    if Classroom.objects.filter(code=course_code).exists():
        storage_code = f"{school.slug}-{course_code}"[:30]

``Classroom.code`` is per-``(school, code)`` unique (``uniq_classroom_school_code``,
academics migration 0085 -- mirroring 0076 for ``Department.code``), so the
database would have accepted school B's own ``X`` alongside school A's ``X``.
The global check rewrote it anyway: a third-party roster system PUT ``X`` and the
row landed as ``<b-slug>-X``, decided entirely by an UNRELATED tenant's data.

Three separate contracts were broken, and each has a test below:

1. Isolation. Another tenant's row must not change what this tenant stores.
2. Identity. The function's own docstring says it matches "by ``(school, code)``",
   and the re-read at the top of the block looks up the UNPREFIXED code. Storing
   the prefixed form means the next PUT misses its own row.
3. Round-trip. The PUT response echoes the SUBMITTED ``classCode`` while the read
   adapter emits the STORED one
   (``apps.interop.oneroster.adapter.classroom_to_oneroster``), so a rewrite made
   PUT and GET disagree about the same class.

The fixture is deliberately two schools; ``test_the_fixture_really_is_two_schools``
and ``test_the_database_accepts_the_same_code_in_both_schools`` are calibration --
without them a green result could mean the writes collapsed onto one school, or
that the rewrite was forced by the engine rather than chosen by the code.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import date
from pathlib import Path

from django.core.cache import cache
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.academics.models import AcademicYear, Classroom, Department
from apps.api import oneroster_writes
from apps.api.oneroster_writes import _upsert_class
from apps.schools.models import School

_TOKEN = "agentq-roster-code-scope"  # nosec B105 -- test-only bearer value


def _make_school(slug: str) -> School:
    # A blank subdomain is unique, so every school in a fixture needs its own.
    return School.objects.create(
        name=slug.replace("-", " ").title(),
        slug=slug,
        subdomain=slug,
        is_active=True,
    )


def _make_year(school: School) -> AcademicYear:
    return AcademicYear.objects.create(
        school=school,
        name="2025/2026",
        start_date=date(2025, 9, 1),
        end_date=date(2026, 6, 30),
        is_active=True,
    )


def _make_dept(school: School, code: str) -> Department:
    return Department.objects.create(school=school, code=code, name="General")


class OneRosterClassCodeIsPerSchoolTests(TestCase):
    """School A holding ``X`` must not change what school B stores for its own ``X``."""

    SHARED_CODE = "PHY101"

    def setUp(self):
        cache.clear()
        self.school_a = _make_school("agentq-roster-a")
        self.school_b = _make_school("agentq-roster-b")
        self.year_a = _make_year(self.school_a)
        self.year_b = _make_year(self.school_b)
        self.dept_a = _make_dept(self.school_a, "AGENTQ-A-GEN")
        self.dept_b = _make_dept(self.school_b, "AGENTQ-B-GEN")
        # School A got there first and holds the contested code.
        self.class_a = Classroom.objects.create(
            school=self.school_a,
            academic_year=self.year_a,
            department=self.dept_a,
            name="Physics 101 (A)",
            code=self.SHARED_CODE,
        )

    # -- calibration ------------------------------------------------------- #

    def test_the_fixture_really_is_two_schools(self):
        """If both halves wrote to one school, 'no collision' would prove nothing."""
        self.assertNotEqual(self.school_a.pk, self.school_b.pk)
        self.assertNotEqual(self.school_a.slug, self.school_b.slug)
        self.assertEqual(
            Classroom.objects.filter(code=self.SHARED_CODE).count(),
            1,
            "fixture drifted: school A should be the only holder before the write",
        )

    def test_the_database_accepts_the_same_code_in_both_schools(self):
        """The rewrite is a CHOICE, not something the engine forced.

        If this raises, the per-school constraint is not in place on the engine
        under test and every other assertion here is meaningless.
        """
        with transaction.atomic():
            twin = Classroom.objects.create(
                school=self.school_b,
                academic_year=self.year_b,
                department=self.dept_b,
                name="Physics 101 (B control)",
                code=self.SHARED_CODE,
            )
        self.assertEqual(twin.code, self.SHARED_CODE)
        self.assertEqual(Classroom.objects.filter(code=self.SHARED_CODE).count(), 2)
        self.assertIn(
            "uniq_classroom_school_code",
            [c.name for c in Classroom._meta.constraints],
            "Classroom no longer declares the per-school unique constraint",
        )

    # -- the defect -------------------------------------------------------- #

    def test_school_b_keeps_its_own_class_code(self):
        payload, status = _upsert_class(
            "agentq-class-b",
            {
                "title": "Physics 101 (B)",
                "classCode": self.SHARED_CODE,
                "school": self.school_b.slug,
            },
        )

        self.assertEqual(status, 201)
        landed = Classroom.objects.filter(school=self.school_b).order_by("pk")
        self.assertEqual(landed.count(), 1, "school B should own exactly one classroom")
        self.assertEqual(
            landed.first().code,
            self.SHARED_CODE,
            "school B's course code was rewritten because ANOTHER tenant holds it",
        )
        self.assertEqual(payload["class"]["classCode"], self.SHARED_CODE)
        # School A is untouched.
        self.class_a.refresh_from_db()
        self.assertEqual(self.class_a.code, self.SHARED_CODE)

    def test_school_b_keeps_its_own_class_code_over_http(self):
        """Same claim through the real PUT endpoint an integration actually calls."""
        with override_settings(RMC_ONEROSTER_ACCESS_TOKEN=_TOKEN):
            response = self.client.put(
                reverse(
                    "api:api-roster-v1p2-put-class",
                    kwargs={"sourced_id": "agentq-class-http"},
                ),
                data={
                    "class": {
                        "sourcedId": "agentq-class-http",
                        "title": "Physics 101 (B http)",
                        "classCode": self.SHARED_CODE,
                        "school": self.school_b.slug,
                    }
                },
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex,
                HTTP_AUTHORIZATION="Bearer " + _TOKEN,
            )

        self.assertEqual(response.status_code, 201, response.content[:400])
        landed = Classroom.objects.get(school=self.school_b)
        self.assertEqual(landed.code, self.SHARED_CODE)

    def test_the_put_response_matches_what_a_later_get_would_report(self):
        """PUT echoes the SUBMITTED code; the read adapter emits the STORED one."""
        from apps.interop.oneroster.adapter import classroom_to_oneroster

        payload, _status = _upsert_class(
            "agentq-class-roundtrip",
            {
                "title": "Physics 101 (B)",
                "classCode": self.SHARED_CODE,
                "school": self.school_b.slug,
            },
        )
        landed = Classroom.objects.get(school=self.school_b)
        read_back = classroom_to_oneroster(landed, self.school_b)
        self.assertEqual(
            payload["class"]["classCode"],
            read_back["classCode"],
            "PUT and GET disagree about the same class's classCode",
        )

    def test_a_repeat_write_is_idempotent_even_if_the_other_tenant_vanishes(self):
        """A roster write is REPEATED; the stored code must not depend on tenant A.

        The rewrite is stable only while school A keeps holding the code. Once A's
        row goes away the global check stops firing, the next PUT stores the
        UNPREFIXED code, and the ``(school, code)`` re-read at the top of the block
        never matched the prefixed row -- so school B ends up with two rows for one
        logical class.
        """
        body = {
            "title": "Physics 101 (B)",
            "classCode": self.SHARED_CODE,
            "school": self.school_b.slug,
        }
        _payload, first_status = _upsert_class("agentq-class-idem", body)
        self.assertEqual(first_status, 201)

        # School A offboards / corrects its catalog. Nothing about school B changed.
        self.class_a.delete()

        _payload2, second_status = _upsert_class("agentq-class-idem", dict(body))
        self.assertEqual(
            second_status,
            200,
            "the repeat write created a new row instead of matching the existing one",
        )
        self.assertEqual(
            Classroom.objects.filter(school=self.school_b).count(),
            1,
            "the repeat write duplicated school B's classroom",
        )

    def test_the_matching_rule_survives_a_repeat_while_the_other_tenant_remains(self):
        """The stable-looking half: two writes with school A still present."""
        body = {
            "title": "Physics 101 (B)",
            "classCode": self.SHARED_CODE,
            "school": self.school_b.slug,
        }
        _p1, s1 = _upsert_class("agentq-class-stable", body)
        _p2, s2 = _upsert_class("agentq-class-stable", dict(body))
        self.assertEqual((s1, s2), (201, 200))
        self.assertEqual(Classroom.objects.filter(school=self.school_b).count(), 1)


class TheGlobalCodeCheckIsGoneTests(TestCase):
    """Source-level: the specific unscoped call, by shape, not 'something changed'.

    A behavioural test can pass for the wrong reason (an empty fixture, a code that
    happens not to collide). This asserts the query itself is scoped, so the guard
    still bites if someone reintroduces the check under a different variable name.
    """

    def test_upsert_class_has_no_unscoped_classroom_code_existence_check(self):
        src = inspect.getsource(oneroster_writes._upsert_class)
        self.assertNotIn(
            "Classroom.objects.filter(code=course_code)",
            src,
            "the existence check is global again: another tenant's code decides "
            "what THIS school stores",
        )

    def test_upsert_class_no_longer_claims_a_global_unique(self):
        src = inspect.getsource(oneroster_writes._upsert_class)
        self.assertNotIn("GLOBALLY-unique", src)
        self.assertNotIn("globally unique", src)


class MintScopedCodeCannotBeVetoedByAnotherTenantTests(TestCase):
    """The sibling marker in ``migration_cloud.landers._helpers.mint_scoped_code``.

    That function probes ``model.objects.filter(code=candidate)`` with no school
    filter, and its marker used to justify the probe by claiming the column is
    unique platform-wide. It is not. The BEHAVIOUR is still benign -- and these
    are the evidence for that claim rather than a restatement of it:

    * the candidate always embeds this school's own ``_scope_token``, so a row
      belonging to another school cannot match it short of a SHA-1 collision on
      the school pk;
    * even when another school is FORCED to hold the exact candidate, the probe
      can only append a hash suffix. It has no veto: both branches return a
      string, so it can never block a create.

    Only the justification was corrected. If someone later scopes the probe (a
    strictly safer default for new code), the first two tests still pass -- they
    assert the outcome, not the query shape.
    """

    def setUp(self):
        self.school_a = _make_school("agentq-mint-a")
        self.school_b = _make_school("agentq-mint-b")

    def _mint(self, school, name="Science"):
        from apps.migration_cloud.landers._helpers import mint_scoped_code

        return mint_scoped_code(
            prefix="DPT", name=name, school=school, model=Department
        )

    def test_two_schools_provisioning_the_same_name_get_different_codes(self):
        """The scope token is what makes a cross-school hit near-impossible."""
        from apps.migration_cloud.landers._helpers import _scope_token

        code_a = self._mint(self.school_a)
        code_b = self._mint(self.school_b)
        self.assertNotEqual(code_a, code_b)
        self.assertIn(_scope_token(self.school_a), code_a)
        self.assertIn(_scope_token(self.school_b), code_b)

    def test_a_neighbour_holding_a_plain_code_does_not_change_this_school(self):
        """The item-1 shape, asked of this function: it does not fire at all."""
        Department.objects.create(
            school=self.school_a, name="Science A", code="SCIENCE"
        )
        before = self._mint(self.school_b)
        self.assertEqual(self._mint(self.school_b), before)
        made = Department.objects.create(
            school=self.school_b, name="Science B", code=before
        )
        self.assertEqual(made.code, before)

    def test_a_forced_cross_school_hit_only_appends_a_suffix(self):
        """Worst case, constructed deliberately: still a usable code, still a create.

        Nothing in the platform mints this row -- the code embeds school B's own
        token. It is written by hand here precisely because that is the only way
        the unscoped branch can be reached across tenants at all.
        """
        plain = self._mint(self.school_b)
        Department.objects.create(
            school=self.school_a, name="Squatter", code=plain
        )

        suffixed = self._mint(self.school_b)
        self.assertNotEqual(suffixed, plain)
        self.assertTrue(suffixed.startswith(plain[:8]))
        self.assertLessEqual(len(suffixed), 30)
        # The probe never blocks: school B still gets its row.
        made = Department.objects.create(
            school=self.school_b, name="Science B", code=suffixed
        )
        self.assertEqual(made.code, suffixed)

    def test_the_probe_has_no_veto(self):
        """Structural: every exit is a string, and nothing raises."""
        import ast

        from apps.migration_cloud.landers import _helpers

        fn = ast.parse(inspect.getsource(_helpers.mint_scoped_code)).body[0]
        exits = [n for n in ast.walk(fn) if isinstance(n, (ast.Return, ast.Raise))]
        self.assertEqual(
            [type(n).__name__ for n in exits],
            ["Return", "Return"],
            "mint_scoped_code gained an exit that is not a plain return",
        )
        for node in exits:
            self.assertIsNotNone(node.value, "a bare return would mint None")
            self.assertFalse(
                isinstance(node.value, ast.Constant) and node.value.value is None,
                "returning None would make the probe a veto",
            )

    def test_the_marker_no_longer_claims_a_platform_wide_unique(self):
        from apps.migration_cloud.landers import _helpers

        src = inspect.getsource(_helpers.mint_scoped_code)
        self.assertNotIn("GLOBALLY-unique", src)
        self.assertNotIn("globally unique", src)
        self.assertIn("uniq_department_school_code", src)


class TheCorrectedJustificationsTests(SimpleTestCase):
    """The rest of the sweep: one live defect, four prose-only sites.

    A comment is the only artefact here a reviewer reads INSTEAD of the code, so
    a false one does more damage than none -- it tells the next person to stop
    looking. These pin the specific false sentences as gone and the real
    constraint as named, rather than merely asserting "something changed".

    The four prose sites were verified school-scoped BEFORE the wording was
    touched; behaviour at those did not change. The seed command was a real
    unscoped lookup and did.
    """

    def _src(self, dotted: str) -> str:
        import importlib

        return Path(importlib.import_module(dotted).__file__).read_text(
            encoding="utf-8"
        )

    def test_the_seed_command_scopes_its_general_department_lookup(self):
        """A live defect, not prose: it resolved an arbitrary tenant's row."""
        src = self._src("apps.academics.management.commands.seed_buea_synthetic")
        self.assertNotIn(
            'Department.objects.filter(code="GEN")',
            src,
            "the GEN lookup is unscoped again: it resolves an arbitrary tenant",
        )
        self.assertIn('school=self.school, code="GEN"', src)

    def test_structure_provisioning_states_the_real_constraint(self):
        src = self._src("apps.academics.structure_provisioning")
        for claim in (
            "``Specialty.code`` is GLOBALLY unique",
            "Classroom.code is GLOBALLY unique",
            "``Specialty.code`` are GLOBALLY unique",
        ):
            self.assertNotIn(claim, src)
        self.assertIn("uniq_specialty_school_code", src)
        self.assertIn("uniq_classroom_school_code", src)
        self.assertIn("uniq_department_school_code", src)

    def test_the_staff_lander_states_the_real_constraint(self):
        src = self._src("apps.migration_cloud.landers.staff_lander")
        self.assertNotIn("globally-unique department code", src)
        self.assertIn("uniq_department_school_code", src)

    def test_the_student_lander_states_the_real_constraint(self):
        src = self._src("apps.migration_cloud.landers.student_lander")
        self.assertNotIn("The globally-unique code is", src)
        self.assertIn("uniq_classroom_school_code", src)
