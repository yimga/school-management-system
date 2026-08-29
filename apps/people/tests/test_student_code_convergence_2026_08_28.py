"""Two nodes minting a placeholder code for ONE row must agree on it.

`student_code` is on the sync rail and is per-school unique. When a student has no
admission number -- the school runs MANUAL admission numbering, or the row is created
before a year/specialty/classroom is chosen -- `save()` invents a placeholder. That
placeholder was random, so the two nodes could not agree, and the disagreement was
permanent: `apply_edge_inserts` upserts by `client_offline_id`, so the two rows are
matched as ONE student, and their differing codes are then a conflict about a value
neither side is more right about.

THE NODE MARK IS EXACTLY WRONG HERE, which is the point worth pinning. On an admission
number the mark is what makes two nodes' numbers differ, and that is its whole purpose --
a box and the cloud must never issue the same number. A placeholder code on one row has
the opposite requirement: the two nodes must land on the SAME string. Stamping the local
node into it guarantees they never do.

So the code is derived from the row's own cross-node identity when it has one, and stays
random only when it has nothing to converge with -- where the mark is useful again,
because it says who invented it.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.people.models import StudentProfile
from apps.schools.models import School


class StudentCodeConvergenceTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Sc {uid}", slug=f"sc-{uid}", subdomain=f"sc{uid}", is_active=True
        )

    def _mint_on_node(self, coid, *, mark, keep=False):
        """What ONE node's save() produces for a row carrying ``coid``.

        The row is removed again unless kept: the other node holds its own copy, and the
        per-school unique index on client_offline_id would otherwise refuse the stand-in.
        """
        with self.settings(RMC_NODE_IDENTIFIER_NAMESPACE=mark):
            student = StudentProfile.objects.create(
                school=self.school,
                first_name="Ada",
                last_name="Nkemelu",
                date_of_birth="2012-01-01",
                client_offline_id=coid,
            )
        code = student.student_code
        if not keep:
            # delete() is a SOFT delete on this model (audit history), so the row and
            # its client_offline_id stay put -- the stand-in then collides with the
            # unique index and the test fails without ever reaching its assertion.
            student.delete(hard_delete=True)
        return code

    def test_two_nodes_mint_the_same_code_for_one_offline_row(self):
        """THE DEFECT. One student, one offline id, two nodes -- one code."""
        coid = "OFFLINE-" + uuid.uuid4().hex
        on_the_box = self._mint_on_node(coid, mark="B")
        in_the_cloud = self._mint_on_node(coid, mark="C")
        self.assertEqual(on_the_box, in_the_cloud)

    def test_the_local_node_mark_is_kept_OUT_of_a_convergent_code(self):
        """Stated separately because it reads like a regression and is the opposite.

        Everything else about identifiers today pushes the node mark IN. A reader who
        removed it from admission numbers would break collision-avoidance; a reader who
        adds it here breaks convergence. The two requirements genuinely differ, so the
        absence is pinned rather than left to look like an oversight.
        """
        coid = "OFFLINE-" + uuid.uuid4().hex
        code = self._mint_on_node(coid, mark="ANNEXA")
        self.assertNotIn("ANNEXA", code)

    def test_a_row_with_no_offline_id_still_says_which_node_invented_its_code(self):
        """Nothing to converge WITH, so the mark earns its place again: the code is
        local by nature, and an operator holding two of them needs to know whose is whose.
        """
        with self.settings(RMC_NODE_IDENTIFIER_NAMESPACE="ANNEXA"):
            student = StudentProfile.objects.create(
                school=self.school, first_name="Bo", last_name="Tabi",
                date_of_birth="2011-05-05", client_offline_id="",
            )
        self.assertIn("ANNEXA", student.student_code)

    def test_two_rows_with_no_offline_id_do_not_collide(self):
        """The random arm still has to be unique WITHIN a node -- the per-school unique
        index on student_code refuses the second row otherwise, and an enrolment fails.
        """
        made = [
            StudentProfile.objects.create(
                school=self.school, first_name=f"S{i}", last_name="X",
                date_of_birth="2011-05-05", client_offline_id="",
            ).student_code
            for i in range(5)
        ]
        self.assertEqual(len(set(made)), 5)

    def test_different_students_get_different_codes(self):
        a = self._mint_on_node("OFFLINE-" + uuid.uuid4().hex, mark="B")
        b = self._mint_on_node("OFFLINE-" + uuid.uuid4().hex, mark="B")
        self.assertNotEqual(a, b)

    def test_the_code_does_not_move_when_the_row_is_saved_again(self):
        coid = "OFFLINE-" + uuid.uuid4().hex
        student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="N",
            date_of_birth="2012-01-01", client_offline_id=coid,
        )
        first = student.student_code
        student.first_name = "Adaeze"
        student.save()
        student.refresh_from_db()
        self.assertEqual(student.student_code, first)

    def test_a_real_admission_number_still_wins(self):
        """The placeholder is a fallback, not a replacement. A row that HAS its permanent
        number must carry that number, or the code stops meaning what the school thinks.
        """
        student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="N",
            date_of_birth="2012-01-01",
            client_offline_id="OFFLINE-" + uuid.uuid4().hex,
            admission_number="26GILC0001",
        )
        self.assertEqual(student.student_code, "26GILC0001")

    def test_the_derived_code_keeps_enough_bits_to_not_collide(self):
        """The digest WIDTH is a safety property, not an implementation detail.

        Two offline ids colliding in one school hit the per-school unique index on
        student_code and the second enrolment is REFUSED -- a child who cannot be
        enrolled, from a shortened hash nobody would think to look at. 64 bits makes
        that unthinkable at any school size; the column allows 50 characters and this
        spends 21, so there is nothing to be won by trimming it.
        """
        code = self._mint_on_node("OFFLINE-" + uuid.uuid4().hex, mark="B")
        self.assertEqual(len(code), len("TEMP-") + 16)

    def test_the_code_fits_the_column(self):
        coid = "OFFLINE-" + "z" * 110  # a client may hand over a long opaque id
        code = self._mint_on_node(coid, mark="B")
        field = StudentProfile._meta.get_field("student_code")
        self.assertLessEqual(len(code), field.max_length)
