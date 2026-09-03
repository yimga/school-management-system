"""A re-import must not overturn a person's deliberate edit -- measured, then fixed.

Measured on 2026-09-02: ``persist_dfv_extras`` (behind every lander via residual
capture) wrote ``DynamicFieldValue`` with a bare ``update_or_create``, so
re-uploading a file silently clobbered values a person had corrected through the
tenant EAV forms or the admin break-glass screen -- and after the fact the two
writers were indistinguishable, because the model carried no provenance of any
kind (``updated_at`` is ``auto_now`` and advances on every write).

The fix is one guarded writer -- ``apps.metadata.services.upsert_dynamic_field_value``
-- and a ``source`` stamp on every write path. These tests hold its contract:

1.  an import may create anything and refresh its own earlier writes;
2.  a value last written by a person is KEPT against a differing import, and the
    disagreement is reported (``record_row_note``), never silent;
3.  an identical value is not rewritten at all -- no ``updated_at`` churn on the
    sync rail, and no downgrading a "human" stamp on a value the import did not
    actually change;
4.  a human write always wins -- people correct imports, not the other way round.
"""

from __future__ import annotations

from django.test import TestCase

from apps.metadata.models import DynamicFieldValue
from apps.metadata.services import (
    SOURCE_HUMAN,
    SOURCE_IMPORT,
    set_dynamic_field_value,
    upsert_dynamic_field_value,
)
from apps.migration_cloud.landers._helpers import (
    dfv_import_source_ref,
    persist_dfv_extras,
)
from apps.migration_cloud.landers.base import LanderContext, LanderResult
from apps.schools.models import School


def _school():
    return School.objects.first() or School.objects.create(
        name="Provenance High", slug="provenance-high", subdomain="provenancehigh"
    )


class UpsertGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = _school()

    def _read(self, entity_id="7", field_key="hair_color"):
        return DynamicFieldValue.objects.get(
            school=self.school,
            entity_type="guard_test",
            entity_id=entity_id,
            field_key=field_key,
        )

    def _write(self, value, source, entity_id="7", field_key="hair_color"):
        return upsert_dynamic_field_value(
            school=self.school,
            entity_type="guard_test",
            entity_id=entity_id,
            field_key=field_key,
            value_json={"v": value},
            source=source,
            source_ref=f"{source}-ref",
        )

    def test_import_creates_and_stamps(self):
        obj, created, preserved = self._write("brown", SOURCE_IMPORT)
        self.assertTrue(created)
        self.assertFalse(preserved)
        self.assertEqual(obj.source, SOURCE_IMPORT)
        self.assertEqual(obj.source_ref, "import-ref")

    def test_import_refreshes_its_own_earlier_write(self):
        self._write("brown", SOURCE_IMPORT)
        _obj, created, preserved = self._write("black", SOURCE_IMPORT)
        self.assertFalse(created)
        self.assertFalse(preserved)
        self.assertEqual(self._read().value_json, {"v": "black"})

    def test_import_also_refreshes_a_legacy_unstamped_row(self):
        # Rows written before the column existed carry source="". Treating them
        # as protected would freeze every residual re-import forever; they get
        # the pre-provenance behaviour, and the first stamped write labels them.
        DynamicFieldValue.objects.create(
            school=self.school,
            entity_type="guard_test",
            entity_id="7",
            field_key="hair_color",
            value_json={"v": "brown"},
        )
        self._write("black", SOURCE_IMPORT)
        row = self._read()
        self.assertEqual(row.value_json, {"v": "black"})
        self.assertEqual(row.source, SOURCE_IMPORT)

    def test_a_deliberate_edit_outranks_the_import(self):
        self._write("brown", SOURCE_IMPORT)
        self._write("auburn", SOURCE_HUMAN)
        _obj, _created, preserved = self._write("brown", SOURCE_IMPORT)
        self.assertTrue(preserved)
        row = self._read()
        self.assertEqual(row.value_json, {"v": "auburn"})
        self.assertEqual(row.source, SOURCE_HUMAN)

    def test_a_person_always_wins_over_anything(self):
        self._write("brown", SOURCE_IMPORT)
        self._write("auburn", SOURCE_HUMAN)
        self._write("grey", SOURCE_HUMAN)
        self.assertEqual(self._read().value_json, {"v": "grey"})

    def test_an_identical_value_is_not_rewritten(self):
        self._write("auburn", SOURCE_HUMAN)
        before = self._read()
        _obj, created, preserved = self._write("auburn", SOURCE_IMPORT)
        self.assertFalse(created)
        self.assertFalse(preserved)
        after = self._read()
        # No write happened: the human stamp survives an import that agrees with
        # it, and updated_at does not churn the sync rail.
        self.assertEqual(after.source, SOURCE_HUMAN)
        self.assertEqual(after.updated_at, before.updated_at)


class ImportWritePathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = _school()
        cls.ctx = LanderContext(
            school=cls.school, bundle_id=8, artifact_id=3, dry_run=False, schema_name=""
        )

    def test_source_ref_names_bundle_and_artifact(self):
        self.assertEqual(dfv_import_source_ref(self.ctx), "bundle:8/artifact:3")

    def test_residual_capture_keeps_a_human_value_and_says_so(self):
        upsert_dynamic_field_value(
            school=self.school,
            entity_type="staff_extras",
            entity_id="55",
            field_key="hire_date",
            value_json={"v": "2019-09-01"},
            source=SOURCE_HUMAN,
            source_ref="user:1",
        )
        res = LanderResult()
        persist_dfv_extras(
            ctx=self.ctx,
            entity_type="staff_extras",
            entity_id="55",
            extras={"hire_date": "2001-01-01"},
            result=res,
        )
        row = DynamicFieldValue.objects.get(
            school=self.school,
            entity_type="staff_extras",
            entity_id="55",
            field_key="hire_date",
        )
        self.assertEqual(row.value_json, {"v": "2019-09-01"})
        self.assertEqual(row.source, SOURCE_HUMAN)
        self.assertTrue(
            any("kept the" in str(n) for n in getattr(res, "notes", []) or []),
            "the disagreement must be reported, not silent",
        )

    def test_residual_capture_stamps_new_rows_as_import(self):
        res = LanderResult()
        persist_dfv_extras(
            ctx=self.ctx,
            entity_type="staff_extras",
            entity_id="56",
            extras={"hire_date": "2015-09-01"},
            result=res,
        )
        row = DynamicFieldValue.objects.get(
            school=self.school,
            entity_type="staff_extras",
            entity_id="56",
            field_key="hire_date",
        )
        self.assertEqual(row.source, SOURCE_IMPORT)
        self.assertEqual(row.source_ref, "bundle:8/artifact:3")


class HumanWritePathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = _school()

    def test_service_setter_stamps_human_by_default(self):
        from apps.academics.models import Department

        dept = Department.objects.create(
            school=self.school, name="Metalwork", code="MET-PR"
        )
        set_dynamic_field_value(dept, "workshop_bay", "B2")
        row = DynamicFieldValue.objects.get(
            school=self.school,
            entity_type="academics.department",
            entity_id=str(dept.pk),
            field_key="workshop_bay",
        )
        self.assertEqual(row.source, SOURCE_HUMAN)
