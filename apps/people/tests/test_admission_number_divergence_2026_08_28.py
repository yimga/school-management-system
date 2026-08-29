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

    def _enrol(self, first, last):
        from apps.people.models import StudentProfile

        return StudentProfile.objects.create(
            school=self.school, first_name=first, last_name=last,
            academic_year=self.year, specialty=self.specialty,
            classroom=self.classroom,
        )

    def test_a_deleted_students_number_is_never_reissued(self):
        """A count goes down when a row is deleted; a counter does not.

        This is the case that used to hand a departed student's admission number to the
        next arrival -- the one value a school treats as permanent, printed on documents
        and filed with the ministry, quietly belonging to two people.
        """
        from apps.people.models import StudentProfile

        self._enrol("ADA", "LOVELACE")
        second = self._enrol("GRACE", "HOPPER")
        issued = second.admission_number
        StudentProfile.objects.filter(pk=second.pk).delete()

        self.assertNotEqual(self._enrol("ALAN", "TURING").admission_number, issued)

    def test_the_counter_does_not_go_backwards_across_many_deletes(self):
        # One delete could be survived by luck. Emptying the year cannot.
        from apps.people.models import StudentProfile

        issued = {self._enrol("S%d" % i, "X").admission_number for i in range(4)}
        StudentProfile.objects.filter(school=self.school).delete()

        after = {self._enrol("T%d" % i, "Y").admission_number for i in range(4)}
        self.assertEqual(issued & after, set())

    def test_a_number_a_legacy_row_already_holds_is_stepped_over(self):
        """A school that deleted students before this existed has issued numbers ABOVE
        its row count, so a counter seeded from that count starts on a number somebody
        already has. What must be unique is the rendered number, not the sequence.
        """
        from apps.people.models import StudentProfile

        first = self._enrol("ADA", "LOVELACE")
        # Someone already holds what a fresh counter would produce next.
        squatter = StudentProfile.objects.create(
            school=self.school, first_name="LEGACY", last_name="ROW",
            academic_year=self.year, specialty=self.specialty,
            classroom=self.classroom,
        )
        taken = squatter.admission_number
        from apps.people.models_identifier_sequence import AdmissionNumberSequence

        AdmissionNumberSequence.objects.filter(school=self.school).update(next_seq=1)

        fresh = self._enrol("ALAN", "TURING").admission_number
        self.assertNotIn(fresh, {first.admission_number, taken})

    def test_a_counter_created_on_an_EXISTING_school_does_not_restart_at_one(self):
        """The seed, and why it is correctness rather than an optimisation.

        Mutation caught this: with the counter seeded at 1 instead of at the school's row
        count, every existing school gets a counter that walks up from the bottom of its
        own number range -- and the first FREE number it finds is precisely the one a
        deleted student used to hold. The defect returns, on exactly the deployments that
        already have students, which is all of them.

        `is_taken` cannot save it: a departed student's number is not taken.
        """
        from apps.people.models import StudentProfile
        from apps.people.models_identifier_sequence import AdmissionNumberSequence

        issued = [self._enrol("S%d" % i, "X").admission_number for i in range(3)]
        # A school that enrolled before this migration existed has no counter row.
        AdmissionNumberSequence.objects.filter(school=self.school).delete()
        StudentProfile.objects.filter(
            school=self.school, admission_number=issued[1]
        ).delete()

        fresh = self._enrol("ALAN", "TURING").admission_number
        self.assertNotIn(fresh, issued)

    def test_each_node_keeps_its_own_number_line(self):
        from apps.people.models_identifier_sequence import AdmissionNumberSequence

        with self.settings(RMC_DEPLOYMENT_PROFILE="edge"):
            self._enrol("ON", "BOX")
        with self.settings(RMC_DEPLOYMENT_PROFILE="online"):
            self._enrol("ON", "CLOUD")

        marks = set(
            AdmissionNumberSequence.objects.filter(school=self.school).values_list(
                "node_code", flat=True
            )
        )
        # Two rows, not one shared counter -- neither node has to ask the other anything,
        # which is what lets a box enrol with the internet down.
        self.assertEqual(marks, {"B", "C"})

    def test_the_counter_is_not_on_the_sync_rail(self):
        # It is local bookkeeping. Syncing it would make two nodes fight over one number
        # line for no benefit, and hand each the other's enrolment count.
        from apps.api.sync_services import _get_entity_config

        config = _get_entity_config(include_derived=True)
        models = {m.__name__ for m, _allowed in config.values()}
        self.assertNotIn("AdmissionNumberSequence", models)


class TheSchoolsOwnPatternMustAcceptTheNewNumbersTests(TestCase):
    """Adding a character to the number can break a rule the school already wrote."""

    def setUp(self):
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Pat {uid}", slug=f"pat-{uid}", subdomain=f"pat{uid}", is_active=True
        )

    def _check(self, policy):
        from apps.siteconfig.identifier_policy_service import pattern_accepts_own_numbers

        return pattern_accepts_own_numbers(self.school, policy=policy)

    @override_settings(RMC_DEPLOYMENT_PROFILE="edge")
    def test_a_pattern_that_would_reject_every_new_enrolment_is_reported(self):
        """`StudentProfile.clean()` enforces admission_number_pattern, so a school whose
        pattern pins the pre-mark shape would have every enrolment of the term refused --
        by its own rule, with a message pointing at the number rather than the pattern.
        Nobody can eyeball five hundred schools' regexes, so this answers it per school.
        """
        ok, sample, _pattern = self._check(
            {"school_code": "GIL", "admission_number_pattern": "^[0-9]{2}GIL[0-9]{4}"}
        )
        self.assertFalse(ok)
        self.assertIn("B", sample)

    @override_settings(RMC_DEPLOYMENT_PROFILE="edge")
    def test_a_pattern_with_room_for_the_mark_is_fine(self):
        ok, _sample, _p = self._check(
            {"school_code": "GIL", "admission_number_pattern": "^[0-9]{2}[A-Z0-9]{2,10}[0-9]{4}"}
        )
        self.assertTrue(ok)

    def test_no_pattern_is_not_a_finding(self):
        ok, _sample, _p = self._check({"school_code": "GIL"})
        self.assertTrue(ok)

    def test_an_uncompilable_pattern_is_not_reported_as_a_rejection(self):
        # Validation cannot enforce what it cannot compile, so this check must not claim
        # the school is broken when the thing that would break is the checker.
        ok, _sample, _p = self._check(
            {"school_code": "GIL", "admission_number_pattern": "^[unclosed"}
        )
        self.assertTrue(ok)


class ThePreviewMatchesWhatIsIssuedTests(TestCase):
    """A format a school validates against has to be the format it is given."""

    def setUp(self):
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Prev {uid}", slug=f"prev-{uid}", subdomain=f"prev{uid}", is_active=True
        )

    @override_settings(RMC_DEPLOYMENT_PROFILE="edge")
    def test_the_preview_shows_the_node_mark_the_school_will_really_get(self):
        """The preview and the mint were two separate copies of one rule, and they HAD
        drifted: the preview knew nothing about the node mark, so a school setting its
        `admission_number_pattern` against the sample would have rejected every real
        enrolment of the term, for a reason nothing on screen explained.
        """
        from apps.siteconfig.identifier_policy_service import preview_admission_number

        self.assertIn("B", preview_admission_number(self.school, seq_4digit="0001"))

    @override_settings(RMC_DEPLOYMENT_PROFILE="edge")
    def test_a_template_placeholder_the_preview_offers_is_one_the_mint_offers(self):
        from apps.siteconfig.identifier_policy_service import render_admission_number

        rendered = render_admission_number(
            {"admission_number_template": "{school_code}/{node_code}/{seq_4digit}"},
            year_2digit="26", school_code="GIL", seq_4digit="0001",
            spec_code="SCI", class_segment="F1", node_code="B",
        )
        self.assertEqual(rendered, "GIL/B/0001")

    def test_an_unknown_placeholder_falls_back_instead_of_failing_enrolment(self):
        # A config typo must not be able to stop a school enrolling anybody.
        from apps.siteconfig.identifier_policy_service import render_admission_number

        rendered = render_admission_number(
            {"admission_number_template": "{no_such_placeholder}"},
            year_2digit="26", school_code="GIL", seq_4digit="0001",
            spec_code="SCI", class_segment="F1", node_code="B",
        )
        self.assertEqual(rendered, "26GILB0001SCIF1")


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
