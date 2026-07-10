"""Land-path tests for the 3 phantom-field-fixed landers (2026-07-09).

The root cause of the silent-data-loss bugs was ZERO land-path coverage: the
catch-all + behavior + alumni landers wrote hand-built kwargs that are NOT model
fields, raised, and were swallowed by broad excepts — so a counter pinned to a
happy number while every row vanished or landed stripped. These tests exercise
each fixed lander end to end against real models and assert the CORRECT field
values persist:

  * DynamicFieldLander (custom_fields): a row LANDS (created>=1, quarantined==0)
    as DynamicFieldValue with value_json + school set (was: 100% quarantined
    "definition unavailable", ZERO landed).
  * BehaviorLander: type -> incident_type mapped, severity mapped, action_taken
    preserved on DFV; distinct same-day incidents stay distinct (collision fix).
  * AlumniLander: status == ALUMNI, and current_employer/current_role/
    graduation_year actually persist on DFV.
"""

from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.academics.models import Incident
from apps.metadata.models import DynamicFieldValue
from apps.migration_cloud.landers.alumni_lander import AlumniLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.behavior_lander import BehaviorLander
from apps.migration_cloud.landers.dynamic_field_lander import DynamicFieldLander
from apps.people.models import StudentProfile
from apps.schools.models import School


class _SchoolFixtureMixin:
    def _school(self, tag: str) -> School:
        return School.objects.create(
            name=f"Lander {tag}", slug=f"lander-{tag}", subdomain=f"lander-{tag}"
        )

    def _ctx(self, school, dry_run=False) -> LanderContext:
        return LanderContext(
            school=school,
            schema_name="",
            bundle_id=None,
            artifact_id=None,
            dry_run=dry_run,
        )


class DynamicFieldLanderLandTests(_SchoolFixtureMixin, TestCase):
    def setUp(self):
        self.school = self._school("df1")

    def test_custom_fields_row_lands_as_dynamic_field_value(self):
        row = {"favorite_club": "Chess", "house": "Blue"}
        result = DynamicFieldLander().land(
            canonical_rows=iter([row]), ctx=self._ctx(self.school)
        )
        # Was the exact failure: every value quarantined "definition unavailable".
        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 2)

        dfv = DynamicFieldValue.objects.get(
            entity_type="migration_artifact", field_key="favorite_club"
        )
        self.assertEqual(dfv.value_json, {"v": "Chess"})
        self.assertEqual(dfv.school_id, self.school.pk)

    def test_rerun_updates_not_duplicates(self):
        lander = DynamicFieldLander()
        ctx = self._ctx(self.school)
        lander.land(canonical_rows=iter([{"house": "Blue"}]), ctx=ctx)
        result = lander.land(canonical_rows=iter([{"house": "Green"}]), ctx=ctx)
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(
            DynamicFieldValue.objects.filter(
                entity_type="migration_artifact", field_key="house"
            ).count(),
            1,
        )
        dfv = DynamicFieldValue.objects.get(
            entity_type="migration_artifact", field_key="house"
        )
        self.assertEqual(dfv.value_json, {"v": "Green"})


class BehaviorLanderLandTests(_SchoolFixtureMixin, TestCase):
    def setUp(self):
        self.school = self._school("bh1")
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Bee",
            last_name="Haver",
            admission_number="ADM-bh1-1",
        )

    def _row(self, **overrides):
        row = {
            "student_external_id": "ADM-bh1-1",
            "date": "2025-09-04",
            "type": "tardy",
            "severity": "high",
            "description": "Late to homeroom",
            "action_taken": "Parent phoned",
        }
        row.update(overrides)
        return row

    def test_type_and_severity_map_to_real_choices(self):
        result = BehaviorLander().land(
            canonical_rows=iter([self._row()]), ctx=self._ctx(self.school)
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 1)

        inc = Incident.objects.get(student=self.student)
        # `type` was a phantom kwarg (field is `incident_type`) -> used to land
        # as the model default OTHER; now mapped.
        self.assertEqual(inc.incident_type, Incident.Type.TARDINESS)
        self.assertEqual(inc.severity, Incident.Severity.HIGH)
        self.assertEqual(inc.description, "Late to homeroom")

    def test_action_taken_preserved_on_dynamic_field_value(self):
        BehaviorLander().land(
            canonical_rows=iter([self._row()]), ctx=self._ctx(self.school)
        )
        inc = Incident.objects.get(student=self.student)
        dfv = DynamicFieldValue.objects.get(
            entity_type="incident", entity_id=str(inc.pk), field_key="action_taken"
        )
        self.assertEqual(dfv.value_json, {"v": "Parent phoned"})
        self.assertEqual(dfv.school_id, self.school.pk)

    def test_distinct_same_day_incidents_do_not_collapse(self):
        # A morning tardy + an afternoon fight on the SAME day must produce TWO
        # Incidents. The old lookup degraded to (student, date) and collapsed
        # them into one.
        rows = [
            self._row(type="tardy", description="Late to homeroom"),
            self._row(type="fight", description="Playground altercation"),
        ]
        result = BehaviorLander().land(
            canonical_rows=iter(rows), ctx=self._ctx(self.school)
        )
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 2)
        incidents = Incident.objects.filter(student=self.student)
        self.assertEqual(incidents.count(), 2)
        self.assertEqual(
            set(incidents.values_list("incident_type", flat=True)),
            {Incident.Type.TARDINESS, Incident.Type.BEHAVIOR},
        )

    def test_identical_rows_dedup(self):
        lander = BehaviorLander()
        ctx = self._ctx(self.school)
        lander.land(canonical_rows=iter([self._row()]), ctx=ctx)
        result = lander.land(canonical_rows=iter([self._row()]), ctx=ctx)
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(Incident.objects.filter(student=self.student).count(), 1)


class AlumniLanderLandTests(_SchoolFixtureMixin, TestCase):
    def setUp(self):
        self.school = self._school("al1")

    def _row(self, **overrides):
        row = {
            "external_id": "ADM-al1-1",
            "first_name": "Aisha",
            "last_name": "Bello",
            "graduation_year": 2018,
            "email": "aisha@example.com",
            "current_employer": "Lagos Tech Co.",
            "current_role": "Senior Engineer",
        }
        row.update(overrides)
        return row

    def test_alumni_lands_with_alumni_status(self):
        result = AlumniLander().land(
            canonical_rows=iter([self._row()]), ctx=self._ctx(self.school)
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 1)

        student = StudentProfile.objects.get(
            admission_number="ADM-al1-1", school=self.school
        )
        # `enrollment_status` was a phantom kwarg dropped by
        # filter_to_model_fields, so status was never set.
        self.assertEqual(student.status, StudentProfile.Status.ALUMNI)

    def test_extras_persist_on_dynamic_field_value(self):
        AlumniLander().land(
            canonical_rows=iter([self._row()]), ctx=self._ctx(self.school)
        )
        student = StudentProfile.objects.get(
            admission_number="ADM-al1-1", school=self.school
        )
        extras = {
            dfv.field_key: dfv.value_json
            for dfv in DynamicFieldValue.objects.filter(
                entity_type="student", entity_id=str(student.pk)
            )
        }
        self.assertEqual(extras.get("current_employer"), {"v": "Lagos Tech Co."})
        self.assertEqual(extras.get("current_role"), {"v": "Senior Engineer"})
        self.assertEqual(extras.get("graduation_year"), {"v": "2018"})
        for dfv in DynamicFieldValue.objects.filter(entity_type="student"):
            self.assertEqual(dfv.school_id, self.school.pk)
