"""Metric-15 scheduling — the persisting generate -> review -> publish flow.

Covers:
  * The Stack-A generator (``TimetableGenerator.generate_schedule``) places every
    demand from a realistic academic graph with ZERO hard violations.
  * The publish gate REFUSES while any hard violation remains, and publishes a
    clean draft.
  * The teacher portal shows only the PUBLISHED schedule (no draft leak).
  * View RBAC: anon -> 302, member-without-permission -> 403, granted -> 200.

Runs on the tenant host (``ttflow.runmycampus.com``) so ``request.school`` is
resolved by the tenant middleware, mirroring ``test_ai_live_http_integration``.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.academics.scheduling import (
    Room,
    Schedule,
    ScheduleEntry,
    TimeSlot,
    TimetableGenerator,
)
from apps.academics.scheduling_evaluation import evaluate_schedule
from apps.accounts.models import Permission, User
from apps.schools.models import School, SchoolMembership

_HOST = "ttflow.runmycampus.com"
_TENANT_URLCONF = "config.tenant_urls"


class _TimetableGraphMixin:
    """Builds a realistic, conflict-solvable academic graph for one school."""

    def build_graph(self, school, uid, *, subject_names=("Math", "English", "Science")):
        year = AcademicYear.objects.create(
            school=school,
            name=f"2025/2026-{uid}",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(school=school, name=f"Dept-{uid}", code=f"D{uid}")
        specialty = Specialty.objects.create(
            school=school, department=dept, name="General", code=f"SP-{uid}"
        )
        classrooms = [
            Classroom.objects.create(
                school=school,
                academic_year=year,
                department=dept,
                name=f"Form {n}",
                code=f"F{n}-{uid}",
            )
            for n in ("A", "B")
        ]
        # One shared teacher per subject (taught in both classrooms) so the
        # generator must actively spread each teacher across distinct slots.
        subjects = []
        teachers = {}
        for sname in subject_names:
            subj = Subject.objects.create(school=school, name=f"{sname}-{uid}")
            subjects.append(subj)
            teachers[subj.id] = User.objects.create_user(
                username=f"tt_{sname.lower()}_{uid}",
                password="Test1234",
                role=User.Role.TEACHER,
            )

        assignments = []
        for classroom in classrooms:
            for subj in subjects:
                sa = SubjectAssignment.objects.create(
                    school=school,
                    academic_year=year,
                    term=term,
                    classroom=classroom,
                    specialty=specialty,
                    subject=subj,
                )
                sa.teachers.add(teachers[subj.id])
                assignments.append(sa)

        # Rooms (global model) — capacity >= any cohort default so all fit.
        rooms = [
            Room.objects.create(
                name=f"Room {i}-{uid}", room_type="CLASSROOM", capacity=40
            )
            for i in range(4)
        ]
        # 4 days x 2 periods = 8 active slots — ample for 6 demands.
        slots = []
        for d in range(4):
            for start_h in (8, 10):
                slot, _created = TimeSlot.objects.get_or_create(
                    day_of_week=d,
                    start_time=time(start_h, 0),
                    end_time=time(start_h + 1, 0),
                    defaults={"slot_name": f"P{start_h}", "is_active": True},
                )
                if not slot.is_active:
                    slot.is_active = True
                    slot.save(update_fields=["is_active"])
                slots.append(slot)

        return {
            "year": year,
            "term": term,
            "dept": dept,
            "specialty": specialty,
            "classrooms": classrooms,
            "subjects": subjects,
            "teachers": teachers,
            "assignments": assignments,
            "rooms": rooms,
            "slots": slots,
        }


class TimetableGeneratorRealisticTests(_TimetableGraphMixin, TestCase):
    """The persisting Stack-A generator produces a conflict-free, complete draft."""

    def setUp(self):
        self.uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Gen School {self.uid}",
            slug=f"gen-{self.uid}",
            subdomain=f"gen-{self.uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"gen_admin_{self.uid}", password="Test1234", role=User.Role.ADMIN
        )
        self.graph = self.build_graph(self.school, self.uid)

    def test_generate_places_all_demands_conflict_free(self):
        generator = TimetableGenerator(self.graph["year"], self.graph["term"])
        schedule = generator.generate_schedule(created_by=self.admin)

        # Every SubjectAssignment (demand) landed a placed entry.
        self.assertEqual(schedule.status, "DRAFT")
        self.assertEqual(
            schedule.entries.count(),
            len(self.graph["assignments"]),
            "generator did not place every demand",
        )

        metrics = evaluate_schedule(schedule)
        self.assertEqual(metrics["entry_count"], len(self.graph["assignments"]))
        self.assertEqual(
            metrics["hard_violations_total"],
            0,
            f"expected a conflict-free schedule, got {metrics['hard_violations']}",
        )


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST])
class TimetablePublishFlowViewTests(_TimetableGraphMixin, TestCase):
    """generate -> review -> publish, publish-refusal, and view RBAC."""

    def setUp(self):
        self.uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="TT Flow School",
            slug="ttflow",
            subdomain="ttflow",
            is_active=True,
        )
        self.graph = self.build_graph(self.school, self.uid)
        self.perm, _ = Permission.objects.get_or_create(
            code="grades.manage", defaults={"name": "Grade & exam management"}
        )

    # -- user/client helpers ------------------------------------------------

    def _member(self, *, role, with_perm=False, username=None):
        user = User.objects.create_user(
            username=username or f"u_{role.lower()}_{uuid.uuid4().hex[:6]}",
            password="Test1234",
            role=role,
            is_staff=(role == User.Role.ADMIN),
        )
        SchoolMembership.objects.create(
            user=user, school=self.school, role=role, is_primary=True
        )
        if with_perm:
            user.feature_permissions.add(self.perm)
        return user

    def _client(self, user):
        c = Client(HTTP_HOST=_HOST)
        c.force_login(user)
        session = c.session
        session["mfa_verified"] = True
        session.save()
        return c

    def _url(self, name, **kwargs):
        return reverse(name, kwargs=kwargs, urlconf=_TENANT_URLCONF)

    def _generate_draft(self, created_by):
        gen = TimetableGenerator(self.graph["year"], self.graph["term"])
        return gen.generate_schedule(created_by=created_by)

    # -- flow: generate ----------------------------------------------------

    def test_generate_creates_persisted_draft_and_redirects_to_review(self):
        admin = self._member(role=User.Role.ADMIN)
        resp = self._client(admin).post(self._url("academics:timetable_generate"))
        self.assertEqual(resp.status_code, 302)
        schedule = Schedule.objects.filter(
            academic_year=self.graph["year"], term=self.graph["term"]
        ).latest("generated_at")
        self.assertEqual(schedule.status, "DRAFT")
        self.assertEqual(
            schedule.entries.count(), len(self.graph["assignments"])
        )
        self.assertIn(f"/timetable/{schedule.id}/review/", resp["Location"])

    # -- flow: publish refuses on conflict ---------------------------------

    def test_publish_refused_while_hard_violation_present(self):
        admin = self._member(role=User.Role.ADMIN)
        schedule = Schedule.objects.create(
            name="Clashing",
            academic_year=self.graph["year"],
            term=self.graph["term"],
            status="DRAFT",
            created_by=admin,
        )
        # Forced COHORT double-book (same classroom + slot, different teacher/room):
        # a hard violation that the DB partial-uniques do NOT block, so it persists.
        cohort = self.graph["classrooms"][0]
        slot = self.graph["slots"][0]
        ScheduleEntry.objects.create(
            schedule=schedule, classroom=cohort, subject=self.graph["subjects"][0],
            teacher=self.graph["teachers"][self.graph["subjects"][0].id],
            room=self.graph["rooms"][0], time_slot=slot,
        )
        ScheduleEntry.objects.create(
            schedule=schedule, classroom=cohort, subject=self.graph["subjects"][1],
            teacher=self.graph["teachers"][self.graph["subjects"][1].id],
            room=self.graph["rooms"][1], time_slot=slot,
        )
        self.assertGreater(evaluate_schedule(schedule)["hard_violations_total"], 0)

        resp = self._client(admin).post(
            self._url("academics:timetable_publish", schedule_id=schedule.id)
        )
        self.assertEqual(resp.status_code, 302)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, "DRAFT", "publish must be refused on clash")
        self.assertIsNone(schedule.published_at)

    def test_publish_succeeds_for_clean_schedule(self):
        admin = self._member(role=User.Role.ADMIN)
        schedule = self._generate_draft(admin)
        self.assertEqual(evaluate_schedule(schedule)["hard_violations_total"], 0)

        resp = self._client(admin).post(
            self._url("academics:timetable_publish", schedule_id=schedule.id)
        )
        self.assertEqual(resp.status_code, 302)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, "PUBLISHED")
        self.assertIsNotNone(schedule.published_at)

    # -- review renders grid + clash panel ---------------------------------

    def test_review_renders_grid_for_owner(self):
        admin = self._member(role=User.Role.ADMIN)
        schedule = self._generate_draft(admin)
        resp = self._client(admin).get(
            self._url("academics:timetable_review", schedule_id=schedule.id)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No clashes detected")
        self.assertContains(resp, "Publish timetable")

    # -- view RBAC ---------------------------------------------------------

    def test_review_anonymous_redirected_to_login(self):
        admin = self._member(role=User.Role.ADMIN)
        schedule = self._generate_draft(admin)
        resp = Client(HTTP_HOST=_HOST).get(
            self._url("academics:timetable_review", schedule_id=schedule.id)
        )
        self.assertEqual(resp.status_code, 302)

    def test_review_member_without_permission_forbidden(self):
        admin = self._member(role=User.Role.ADMIN)
        schedule = self._generate_draft(admin)
        teacher = self._member(role=User.Role.TEACHER, with_perm=False)
        resp = self._client(teacher).get(
            self._url("academics:timetable_review", schedule_id=schedule.id)
        )
        self.assertEqual(resp.status_code, 403)

    def test_review_member_with_permission_code_allowed(self):
        admin = self._member(role=User.Role.ADMIN)
        schedule = self._generate_draft(admin)
        granted = self._member(role=User.Role.TEACHER, with_perm=True)
        resp = self._client(granted).get(
            self._url("academics:timetable_review", schedule_id=schedule.id)
        )
        self.assertEqual(resp.status_code, 200)

    # -- tenant isolation --------------------------------------------------

    def test_review_other_school_schedule_is_404(self):
        admin = self._member(role=User.Role.ADMIN)
        other = School.objects.create(
            name="Other", slug=f"other-{self.uid}", subdomain=f"other-{self.uid}",
            is_active=True,
        )
        other_graph = self.build_graph(other, f"o{self.uid[:6]}")
        other_schedule = Schedule.objects.create(
            name="Other draft", academic_year=other_graph["year"],
            term=other_graph["term"], status="DRAFT", created_by=admin,
        )
        resp = self._client(admin).get(
            self._url("academics:timetable_review", schedule_id=other_schedule.id)
        )
        self.assertEqual(resp.status_code, 404)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST])
class TeacherTimetableDraftLeakTests(_TimetableGraphMixin, TestCase):
    """The teacher portal shows the PUBLISHED schedule only — never a draft."""

    def setUp(self):
        self.uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="Leak School", slug="ttflow", subdomain="ttflow", is_active=True,
        )
        self.graph = self.build_graph(self.school, self.uid)
        # This school's year/term must be THE globally-active pair, because
        # teacher_timetable resolves the active term without a school arg.
        AcademicYear.objects.exclude(pk=self.graph["year"].pk).update(is_active=False)
        Term.objects.exclude(pk=self.graph["term"].pk).update(is_active=False)

        self.teacher = User.objects.create_user(
            username=f"leak_teacher_{self.uid}", password="Test1234",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=self.teacher, school=self.school, role=User.Role.TEACHER,
            is_primary=True,
        )

        subj = self.graph["subjects"][0]
        cohort = self.graph["classrooms"][0]
        room = self.graph["rooms"][0]
        # PUBLISHED schedule with the teacher's class at slot 0.
        self.published = Schedule.objects.create(
            name="Published", academic_year=self.graph["year"],
            term=self.graph["term"], status="PUBLISHED",
            published_at=timezone.now(), created_by=self.teacher,
        )
        ScheduleEntry.objects.create(
            schedule=self.published, classroom=cohort, subject=subj,
            teacher=self.teacher, room=room, time_slot=self.graph["slots"][0],
        )
        # DRAFT schedule with the teacher's class at a DIFFERENT slot (distinct
        # (term, teacher, slot) so the partial-unique does not fire).
        self.draft = Schedule.objects.create(
            name="Draft", academic_year=self.graph["year"],
            term=self.graph["term"], status="DRAFT", created_by=self.teacher,
        )
        ScheduleEntry.objects.create(
            schedule=self.draft, classroom=cohort, subject=subj,
            teacher=self.teacher, room=room, time_slot=self.graph["slots"][1],
        )

    def test_teacher_sees_published_not_draft(self):
        c = Client(HTTP_HOST=_HOST)
        c.force_login(self.teacher)
        session = c.session
        session["mfa_verified"] = True
        session.save()
        resp = c.get(reverse("portal:teacher_timetable", urlconf=_TENANT_URLCONF))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["schedule"].pk, self.published.pk)
        self.assertNotEqual(resp.context["schedule"].pk, self.draft.pk)
