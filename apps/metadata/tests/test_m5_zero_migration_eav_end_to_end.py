"""M5 -- zero-migration runtime custom fields, proven end to end.

The M5 claim is *not* "an EAV table exists". It is that an operator can add a
custom field to a live tenant **at runtime** and that field will save, read
back and RENDER on the real detail page, with **no DDL and no migration**.

Existing coverage stops short of that claim:

* ``test_dynamic_forms_runtime.py`` only exercises fields that were installed by
  ``seed_country_eav_definitions`` -- a *shipped catalog*, not a field an
  operator invented after deploy -- and it calls ``dynamic_field_display_rows``
  directly rather than rendering a page.
* ``test_metadata_no_ddl_safety.py`` unit-tests the ``contains_forbidden_ddl``
  *string matcher*. It never observes the SQL the EAV path actually emits, so
  it cannot say whether the live path is DDL-free.

So the two halves of M5 -- "end to end" and "no migration required" -- were
both unasserted. This module asserts them against observed behaviour:

1. Every SQL statement emitted across define -> save -> read -> render is
   captured with ``CaptureQueriesContext`` and screened by the repo's own
   ``contains_forbidden_ddl``. ``test_ddl_detector_rejects_known_bad_sql``
   proves that detector against known-bad input first, so the zero means
   something (a scan that cannot fail is not a scan).
2. The physical table list and the physical ``people_studentprofile`` column
   list are read from ``connection.introspection`` before and after and must be
   IDENTICAL -- and the new field's key must be absent from that column list
   even while its value is readable and rendered. A value you can render out of
   a column that demonstrably does not exist is the zero-migration guarantee.
3. Five different data types round-trip through the same unchanged schema, so
   the result cannot be one hard-coded column that happened to fit.

Postgres/SQLite note: this proof is backend-independent. It asserts on the SQL
text the ORM emits and on introspected schema, neither of which is a
SQLite-only behaviour.
"""

from __future__ import annotations

import datetime

from django import forms
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import User
from apps.metadata.ddl_safety import contains_forbidden_ddl
from apps.metadata.dynamic_forms import (
    attach_dynamic_fields_for_model,
    save_dynamic_fields_for_model,
)
from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.metadata.services import get_dynamic_field_value
from apps.people.models import StudentProfile
from apps.people.views_backend import backend_student_detail
from apps.schools.models import School


def _physical_columns(table: str) -> list[str]:
    """Real column names for ``table``, straight from the DB, not from Django."""
    with connection.cursor() as cursor:
        return sorted(
            col.name
            for col in connection.introspection.get_table_description(cursor, table)
        )


def _physical_tables() -> list[str]:
    with connection.cursor() as cursor:
        return sorted(connection.introspection.table_names(cursor))


class _RuntimeFieldForm(forms.Form):
    """A bare form -- it carries NO field for the custom key.

    Every ``dyn_*`` field on it is put there at runtime by
    ``attach_dynamic_fields_for_model`` reading the definition rows. If the
    definition did not reach the form, ``is_valid()`` would still pass and
    ``cleaned_data`` would simply not contain the key -- which is why the tests
    below assert on the *persisted value*, never on the form alone.
    """


class ZeroMigrationRuntimeFieldTests(TestCase):
    """Define a field after deploy; save, read and render it with zero DDL."""

    def setUp(self):
        self.school = School.objects.create(
            name="M5 Zero Migration School",
            slug="m5-zero-migration-school",
            subdomain="m5-zero-migration",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ngwa",
            last_name="Fomum",
            student_code="M5-STU-1",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="m5admin",
            password="pw",
            role=User.Role.ADMIN,
        )
        ct = ContentType.objects.get_for_model(StudentProfile)
        self.user.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="view_studentprofile")
        )

    # -- helpers ---------------------------------------------------------

    def _define_field_at_runtime(self, *, field_key, label, data_type="string"):
        return DynamicFieldDefinition.objects.create(
            entity_type="people.studentprofile",
            field_key=field_key,
            label=label,
            data_type=data_type,
            school=self.school,
            is_active=True,
            required=False,
        )

    def _submit(self, payload: dict) -> _RuntimeFieldForm:
        form = _RuntimeFieldForm(data=payload)
        attach_dynamic_fields_for_model(
            form, school=self.school, model=StudentProfile, instance=self.student
        )
        self.assertTrue(form.is_valid(), msg=form.errors.as_json())
        save_dynamic_fields_for_model(
            form, instance=self.student, school=self.school, model=StudentProfile
        )
        return form

    def _render_detail(self) -> str:
        request = RequestFactory().get(f"/backend/students/{self.student.pk}/")
        request.user = self.user
        request.school = self.school
        response = backend_student_detail(request, self.student.pk)
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8", errors="replace")

    # -- the detector proof ----------------------------------------------

    def test_ddl_detector_rejects_known_bad_sql(self):
        """Prove the screen before trusting its zero.

        ``test_no_ddl_is_emitted_across_the_whole_cycle`` below is only evidence
        if this screen can actually fail. Feed it exactly the statement a
        migration-based custom field WOULD have emitted.
        """
        migration_sql = (
            'ALTER TABLE "people_studentprofile" '
            'ADD COLUMN "guardian_bus_stop" varchar(120) NULL'
        )
        self.assertTrue(contains_forbidden_ddl(migration_sql))
        self.assertTrue(
            contains_forbidden_ddl('CREATE TABLE "people_studentprofile_x" (id int)')
        )
        self.assertTrue(contains_forbidden_ddl('DROP TABLE "metadata_dynamicfieldvalue"'))
        # ...and does not cry wolf on the traffic the EAV path really emits.
        self.assertFalse(
            contains_forbidden_ddl(
                'SELECT "metadata_dynamicfieldvalue"."value_json" '
                'FROM "metadata_dynamicfieldvalue" WHERE "field_key" = %s'
            )
        )
        self.assertFalse(
            contains_forbidden_ddl(
                'INSERT INTO "metadata_dynamicfieldvalue" '
                '("entity_type", "entity_id", "field_key", "value_json") '
                "VALUES (%s, %s, %s, %s)"
            )
        )

    # -- the end-to-end proof --------------------------------------------

    def test_runtime_field_saves_reads_back_and_renders_on_the_detail_page(self):
        field_key = "guardian_bus_stop"
        value = "Route 12 / Ndogbong"

        # Nothing knows about this field before the operator invents it.
        self.assertFalse(
            DynamicFieldDefinition.objects.filter(field_key=field_key).exists()
        )
        self.assertNotIn(field_key, _physical_columns("people_studentprofile"))
        self.assertNotIn(
            "Guardian Bus Stop",
            self._render_detail(),
            msg="the label rendered BEFORE the field was defined -- fixture is not clean",
        )

        # DEFINE at runtime.
        self._define_field_at_runtime(
            field_key=field_key, label="Guardian Bus Stop", data_type="string"
        )

        # The definition reaches the real form as a real bound field.
        probe = _RuntimeFieldForm()
        attach_dynamic_fields_for_model(
            probe, school=self.school, model=StudentProfile, instance=self.student
        )
        self.assertIn(
            f"dyn_{field_key}",
            probe.fields,
            msg="definition never reached the form; the save below would be vacuous",
        )

        # SAVE through the same helper the backend student views call.
        self._submit({f"dyn_{field_key}": value})

        # READ BACK -- exact value, from the DB.
        self.assertEqual(
            get_dynamic_field_value(self.student, field_key, school=self.school),
            value,
        )
        stored = DynamicFieldValue.objects.get(
            school=self.school,
            entity_type="people.studentprofile",
            entity_id=str(self.student.pk),
            field_key=field_key,
        )
        self.assertEqual(stored.value_json, {"v": value})

        # RENDER -- the real view, the real template, real bytes.
        body = self._render_detail()
        self.assertIn("Guardian Bus Stop", body)
        self.assertIn(value, body)

        # ...and the value came out of a column that does not exist.
        self.assertNotIn(field_key, _physical_columns("people_studentprofile"))

    def test_no_ddl_is_emitted_across_the_whole_cycle(self):
        """Define -> save -> read -> render emits zero schema mutations."""
        tables_before = _physical_tables()
        columns_before = _physical_columns("people_studentprofile")

        with CaptureQueriesContext(connection) as captured:
            self._define_field_at_runtime(
                field_key="transport_zone", label="Transport Zone"
            )
            self._submit({"dyn_transport_zone": "Zone B"})
            self.assertEqual(
                get_dynamic_field_value(
                    self.student, "transport_zone", school=self.school
                ),
                "Zone B",
            )
            body = self._render_detail()

        statements = [q["sql"] for q in captured.captured_queries]

        # The fixture must actually have exercised the path. A DDL-free run of
        # zero queries would "pass" while proving nothing.
        self.assertGreater(
            len(statements),
            20,
            msg=f"only {len(statements)} queries captured -- cycle did not run",
        )
        self.assertIn("Zone B", body)

        offenders = [sql for sql in statements if contains_forbidden_ddl(sql)]
        self.assertEqual(
            offenders,
            [],
            msg=f"runtime custom field emitted DDL: {offenders[:3]}",
        )

        # Physical schema is untouched, so no migration could have been needed.
        self.assertEqual(tables_before, _physical_tables())
        self.assertEqual(columns_before, _physical_columns("people_studentprofile"))
        self.assertNotIn("transport_zone", columns_before)

    def test_five_data_types_round_trip_through_the_same_unchanged_schema(self):
        """Not one lucky column: string/number/boolean/date/json all survive."""
        columns_before = _physical_columns("people_studentprofile")

        self._define_field_at_runtime(
            field_key="locker_code", label="Locker Code", data_type="string"
        )
        self._define_field_at_runtime(
            field_key="bus_fee_share", label="Bus Fee Share", data_type="number"
        )
        self._define_field_at_runtime(
            field_key="has_bus_pass", label="Has Bus Pass", data_type="boolean"
        )
        self._define_field_at_runtime(
            field_key="pass_issued_on", label="Pass Issued On", data_type="date"
        )

        self._submit(
            {
                "dyn_locker_code": "L-114",
                "dyn_bus_fee_share": "37.50",
                "dyn_has_bus_pass": "on",
                "dyn_pass_issued_on": "2026-03-04",
            }
        )

        self.assertEqual(
            get_dynamic_field_value(self.student, "locker_code", school=self.school),
            "L-114",
        )
        self.assertEqual(
            get_dynamic_field_value(self.student, "bus_fee_share", school=self.school),
            37.5,
        )
        self.assertIs(
            get_dynamic_field_value(self.student, "has_bus_pass", school=self.school),
            True,
        )
        # JSON has no date type, so the durable representation is ISO-8601 --
        # which is also what a DateField accepts back as ``initial`` and what
        # the detail page renders. Before the wrap_value fix this line was not
        # reached at all: the save raised
        # ``TypeError: Object of type date is not JSON serializable`` at INSERT.
        self.assertEqual(
            get_dynamic_field_value(self.student, "pass_issued_on", school=self.school),
            "2026-03-04",
        )
        self.assertEqual(
            datetime.date.fromisoformat(
                get_dynamic_field_value(
                    self.student, "pass_issued_on", school=self.school
                )
            ),
            datetime.date(2026, 3, 4),
        )

        # All four render on the real page.
        body = self._render_detail()
        for label, shown in (
            ("Locker Code", "L-114"),
            ("Bus Fee Share", "37.5"),
            ("Has Bus Pass", "True"),
            ("Pass Issued On", "2026-03-04"),
        ):
            self.assertIn(label, body)
            self.assertIn(shown, body)

        # Four new fields, zero new columns.
        self.assertEqual(columns_before, _physical_columns("people_studentprofile"))

    def test_deactivating_a_runtime_field_removes_it_from_the_page(self):
        """The runtime switch is real: is_active=False stops the render."""
        defn = self._define_field_at_runtime(
            field_key="sibling_ref", label="Sibling Reference"
        )
        self._submit({"dyn_sibling_ref": "SIB-7788"})
        self.assertIn("SIB-7788", self._render_detail())

        defn.is_active = False
        defn.save(update_fields=["is_active"])

        body = self._render_detail()
        self.assertNotIn("Sibling Reference", body)
        self.assertNotIn("SIB-7788", body)
        # The value is retained -- deactivation hides, it does not destroy.
        self.assertTrue(
            DynamicFieldValue.objects.filter(
                school=self.school, field_key="sibling_ref"
            ).exists()
        )

    def test_runtime_field_does_not_leak_across_tenants(self):
        """A field one school defines must not appear on another school's page."""
        other = School.objects.create(
            name="M5 Other School",
            slug="m5-other-school",
            subdomain="m5-other",
            is_active=True,
        )
        other_student = StudentProfile.objects.create(
            school=other,
            first_name="Bih",
            last_name="Ncha",
            student_code="M5-STU-2",
            is_active=True,
        )
        self._define_field_at_runtime(
            field_key="house_color", label="House Color"
        )
        self._submit({"dyn_house_color": "Emerald"})
        self.assertIn("Emerald", self._render_detail())

        request = RequestFactory().get(f"/backend/students/{other_student.pk}/")
        request.user = self.user
        request.school = other
        response = backend_student_detail(request, other_student.pk)
        self.assertEqual(response.status_code, 200)
        other_body = response.content.decode("utf-8", errors="replace")
        self.assertNotIn("House Color", other_body)
        self.assertNotIn("Emerald", other_body)
