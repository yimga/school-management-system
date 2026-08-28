"""Two nodes issuing identifiers must not be able to issue the same one.

An admission number is minted from `count() + 1` on whichever node is running, and
`student_code` defaults to it. That code IS on the sync rail and IS per-school unique, so
when two nodes issue the same number the second copy to arrive is refused with 422 -- and
that student never lands, on that attempt or any later one, because nothing about a retry
changes the number. A box with 40 students and a cloud with 41 hand the same new arrival
two different numbers today; they will hand two different arrivals the SAME number as soon
as the counts line up.

The fix is a mark in the number saying which node issued it. No coordination, so a box cut
off from the internet still enrols, and collision becomes impossible rather than unlikely.
What it deliberately does NOT do is change any number already issued.

STILL OPEN, and these tests say so rather than implying otherwise: the sequence is a row
count, so deleting a student hands their number to the next arrival. That is a within-node
defect the mark does not touch, and fixing it needs a counter that survives deletion.
"""

from __future__ import annotations

import uuid

from django.test import TestCase, override_settings


class TheNodeMarkTests(TestCase):
    """Where the mark comes from, in the order the cascade says."""

    def setUp(self):
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Mark {uid}", slug=f"mark-{uid}", subdomain=f"mark{uid}", is_active=True
        )

    def _mark(self, **kw):
        from apps.siteconfig.identifier_policy_service import node_identifier_namespace

        return node_identifier_namespace(self.school, **kw)

    @override_settings(RMC_DEPLOYMENT_PROFILE="edge")
    def test_a_box_and_a_cloud_do_not_call_themselves_the_same_thing(self):
        box = self._mark()
        with self.settings(RMC_DEPLOYMENT_PROFILE="online"):
            cloud = self._mark()
        self.assertNotEqual(box, cloud)

    @override_settings(
        RMC_DEPLOYMENT_PROFILE="edge", RMC_NODE_IDENTIFIER_NAMESPACE="ANNEX"
    )
    def test_the_deployment_may_name_itself(self):
        # A school with two boxes needs them to differ from EACH OTHER, not merely from
        # the cloud -- so the profile cannot be the last word.
        self.assertEqual(self._mark(), "ANNEX")

    @override_settings(RMC_NODE_IDENTIFIER_NAMESPACE="ANNEX")
    def test_the_school_outranks_the_deployment(self):
        # It is the school's document and the school's numbering. The cascade puts the
        # tenant first everywhere else; this is not the place to invert it.
        self.assertEqual(self._mark(policy={"node_code": "MAIN"}), "MAIN")

    @override_settings(RMC_NODE_IDENTIFIER_NAMESPACE="ANNEXA")
    def test_a_long_mark_is_kept_whole_rather_than_silently_shortened(self):
        """Truncating would merge ANNEXA and ANNEXB back into one mark.

        That is the collision this whole mechanism exists to prevent, reintroduced by the
        mechanism itself and reported nowhere. An over-long mark is a visible problem in
        the first number issued; a silently shortened one is not a problem until two
        students cannot both enrol.
        """
        self.assertEqual(self._mark(), "ANNEXA")
        with self.settings(RMC_NODE_IDENTIFIER_NAMESPACE="ANNEXB"):
            self.assertEqual(self._mark(), "ANNEXB")

    @override_settings(RMC_NODE_IDENTIFIER_NAMESPACE="b-1 !!")
    def test_a_stray_value_cannot_break_the_number_it_lands_in(self):
        """A school validates its admission numbers against its own pattern.

        A mark carrying punctuation or a space would produce numbers that fail that
        pattern -- so every one of a term's enrolments would be rejected by a rule the
        school itself set, for a reason nothing on screen would explain.
        """
        self.assertEqual(self._mark(), "B1")

    @override_settings(RMC_DEPLOYMENT_PROFILE="something-nobody-registered")
    def test_an_unknown_profile_still_yields_a_usable_mark(self):
        # Refusing to mint would take enrolment down over a typo in an env var.
        self.assertTrue(self._mark().isalnum())


class TheNumberCarriesTheMarkTests(TestCase):
    """Every path that issues a number, not just the default one."""

    def setUp(self):
        from apps.academics.models import (
            AcademicYear, Classroom, Department, Specialty,
        )
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Adm {uid}", slug=f"adm-{uid}", subdomain=f"adm{uid}", is_active=True
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date="2026-09-01", end_date="2027-07-31",
        )
        self.department = Department.objects.create(
            school=self.school, name="Sciences", code="SCID"
        )
        self.specialty = Specialty.objects.create(
            school=self.school, department=self.department, name="Science", code="SCI"
        )
        self.classroom = Classroom.objects.create(
            school=self.school, department=self.department, name="Form 1",
            code="F1", academic_year=self.year,
        )

    def _generate(self):
        from apps.people.models import StudentProfile

        return StudentProfile.generate_admission_number(
            self.year, self.specialty, self.classroom, school=self.school
        )

    def _with_policy(self, admissions):
        """Swap the policy resolver for one call. Returns a restore callable."""
        from apps.policies import policy_registry

        original = policy_registry.get_effective_policy
        policy_registry.get_effective_policy = lambda school, *a, **kw: {
            "admissions": admissions
        }
        return original

    def test_the_same_row_count_on_two_nodes_no_longer_yields_the_same_number(self):
        """THE defect, stated as the thing that must not happen.

        Both nodes are at exactly the same count -- the case where the old code was
        guaranteed to collide, not merely likely to.
        """
        with self.settings(RMC_DEPLOYMENT_PROFILE="edge"):
            on_the_box = self._generate()
        with self.settings(RMC_DEPLOYMENT_PROFILE="online"):
            on_the_cloud = self._generate()

        self.assertNotEqual(on_the_box, on_the_cloud)

    def test_seq_only_carries_it_too(self):
        """The shortest format a school can pick is the one most certain to collide.

        SEQ_ONLY is four digits of a local row count and nothing else, so two nodes at the
        same count produce the identical string. Skipping the mark here because the format
        is "meant to be short" would leave the collision exactly where it is most likely.
        """
        from apps.policies import policy_registry

        original = self._with_policy({"admission_number_strategy": "SEQ_ONLY"})
        try:
            with self.settings(RMC_DEPLOYMENT_PROFILE="edge"):
                box = self._generate()
            with self.settings(RMC_DEPLOYMENT_PROFILE="online"):
                cloud = self._generate()
        finally:
            policy_registry.get_effective_policy = original

        self.assertNotEqual(box, cloud)

    def test_year_seq_carries_it_too(self):
        """The third built-in strategy, and the one the first pass forgot.

        Mutation caught this: FULL and SEQ_ONLY were tested and YEAR_SEQ was not, so
        dropping the mark from it changed nothing any test could see. A school on that
        strategy would have collided exactly as before, and the suite would have said the
        node mark was covered.
        """
        from apps.policies import policy_registry

        original = self._with_policy({"admission_number_strategy": "YEAR_SEQ"})
        try:
            with self.settings(RMC_DEPLOYMENT_PROFILE="edge"):
                box = self._generate()
            with self.settings(RMC_DEPLOYMENT_PROFILE="online"):
                cloud = self._generate()
        finally:
            policy_registry.get_effective_policy = original

        self.assertNotEqual(box, cloud)

    def test_a_school_template_can_place_the_mark_itself(self):
        # The school owns the shape of its own number, so the mark is offered as a
        # placeholder rather than forced into a position we picked for them.
        from apps.policies import policy_registry

        original = self._with_policy(
            {"admission_number_template": "{school_code}/{node_code}/{seq_4digit}"}
        )
        try:
            with self.settings(RMC_DEPLOYMENT_PROFILE="edge"):
                number = self._generate()
        finally:
            policy_registry.get_effective_policy = original

        self.assertIn("/B/", number)

    def test_a_temp_code_says_which_node_minted_it(self):
        """The random fallback still cannot converge, and that is not what this fixes.

        Two nodes minting for one student produce two random codes and neither is more
        right. What the mark buys is that an operator holding a pile of code conflicts can
        see which side issued each one.
        """
        from apps.people.models import StudentProfile

        with self.settings(RMC_DEPLOYMENT_PROFILE="edge"):
            bare = StudentProfile.objects.create(
                school=self.school, first_name="ADA", last_name="LOVELACE"
            )
        self.assertTrue(bare.student_code.startswith("TEMP-B-"))

    def test_the_sequence_still_hands_a_deleted_students_number_back(self):
        """NOT FIXED, and pinned so nobody reads the mark as a full repair.

        The sequence is `count() + 1`, so it is neither monotonic nor unique over time.
        The mark stops two nodes colliding with each other; it does nothing about one node
        reissuing a number it already gave away. Fixing that needs a counter that survives
        a delete -- a table and a migration.
        """
        from apps.people.models import StudentProfile

        def _enrol(first, last):
            return StudentProfile.objects.create(
                school=self.school, first_name=first, last_name=last,
                academic_year=self.year, specialty=self.specialty,
                classroom=self.classroom,
            )

        _enrol("ADA", "LOVELACE")
        second = _enrol("GRACE", "HOPPER")
        issued = second.admission_number
        StudentProfile.objects.filter(pk=second.pk).delete()

        self.assertEqual(_enrol("ALAN", "TURING").admission_number, issued)


class TheRailCarriesTheNumberTests(TestCase):
    """Without this the receiver re-mints, and the divergence is silent."""

    def test_admission_number_is_on_the_rail_beside_the_code_it_produces(self):
        from apps.api.sync_services import _get_entity_config

        _model, allowed = _get_entity_config(include_derived=True)["student"]
        self.assertIn("student_code", allowed)
        # Shipping the code without its source is what let the receiving node regenerate
        # the number from its OWN row count -- and never report it, because a field that
        # is not on the rail is never compared.
        self.assertIn("admission_number", allowed)


class WhatACollisionStillDoesTests(TestCase):
    """The mark prevents a collision; it does not make one survivable.

    Kept because the consequence is what justifies the change, and because the seven
    duplicated numbers already in the real register will hit exactly this.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Rail {uid}", slug=f"rail-{uid}", subdomain=f"rail{uid}", is_active=True
        )
        self.user = get_user_model().objects.create(
            username=f"railadm{uid}", email=f"railadm{uid}@example.test",
            is_staff=True, is_superuser=True,
        )

    def test_a_code_the_other_node_already_issued_refuses_the_student(self):
        from apps.api.sync_services import apply_edge_inserts
        from apps.people.models import StudentProfile

        StudentProfile.objects.create(
            school=self.school, first_name="GRACE", last_name="HOPPER",
            student_code="24GIL0173PL2",
        )

        out = apply_edge_inserts(
            self.school.pk,
            self.user,
            [{
                "entity_type": "student",
                "client_offline_id": f"box-{uuid.uuid4().hex[:8]}",
                "changes": {
                    "first_name": "ALAN", "last_name": "TURING",
                    "student_code": "24GIL0173PL2",
                },
            }],
            sync_origin="edge-push",
        )

        self.assertEqual(out["created"], 0)
        self.assertEqual(out["results"][0]["status"], 422)
        # `insert_failed` is the edge-insert path's own label; the update path in the same
        # module says `create_failed`. Pinned to the one this path actually emits.
        self.assertEqual(out["results"][0]["data"]["error"], "insert_failed")
        self.assertFalse(
            StudentProfile.objects.filter(
                school=self.school, first_name="ALAN"
            ).exists()
        )
