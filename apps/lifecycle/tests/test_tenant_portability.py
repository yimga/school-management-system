"""Full-fidelity tenant portability — export/import round-trip + fail-closed checks."""
import json
import uuid

from django.db.models import QuerySet
from django.test import SimpleTestCase, TestCase

from apps.lifecycle.tenant_portability import (
    _direct_school_field,
    _label,
    _school_lookup_path,
    _scope_queryset,
    _tenant_models,
    export_tenant_bundle,
    import_tenant_bundle,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


def _school():
    tag = uuid.uuid4().hex[:8]
    return School.objects.create(
        name="Gilead Tech High", slug=f"gilead-{tag}", subdomain=f"gilead-{tag}", is_active=True
    )


class TenantPortabilityRoundTripTests(TestCase):
    def test_round_trip_preserves_rows_and_pks(self):
        school = _school()
        s1 = StudentProfile.objects.create(school=school, first_name="Ada", last_name="Njoya")
        s2 = StudentProfile.objects.create(school=school, first_name="Ben", last_name="Fon")
        s1_pk, s2_pk = s1.pk, s2.pk

        bundle = export_tenant_bundle(school)
        # The container is signed JSON carrying the school id.
        container = json.loads(bundle)
        self.assertEqual(container["school_id"], str(school.id))
        self.assertIn("sig", container)

        # Wipe the operational rows, then restore from the bundle.
        StudentProfile.objects.filter(school=school).delete()
        self.assertFalse(StudentProfile.objects.filter(pk=s1_pk).exists())

        result = import_tenant_bundle(bundle, expected_school_id=school.id)

        # Restored with identical pks and field values.
        self.assertTrue(StudentProfile.objects.filter(pk=s1_pk).exists())
        self.assertTrue(StudentProfile.objects.filter(pk=s2_pk).exists())
        self.assertEqual(StudentProfile.objects.get(pk=s1_pk).first_name, "Ada")
        self.assertEqual(StudentProfile.objects.get(pk=s2_pk).last_name, "Fon")
        self.assertGreaterEqual(result["total"], 2)
        self.assertIn("people.studentprofile", result["imported"])

    def test_reimport_is_idempotent(self):
        school = _school()
        StudentProfile.objects.create(school=school, first_name="Ada", last_name="Njoya")
        bundle = export_tenant_bundle(school)
        import_tenant_bundle(bundle, expected_school_id=school.id)
        import_tenant_bundle(bundle, expected_school_id=school.id)  # second run must not duplicate
        self.assertEqual(StudentProfile.objects.filter(school=school).count(), 1)

    def test_tampered_signature_is_rejected_before_decrypt(self):
        school = _school()
        StudentProfile.objects.create(school=school, first_name="Ada", last_name="Njoya")
        container = json.loads(export_tenant_bundle(school))
        container["sig"] = "0" * 64  # forged signature
        with self.assertRaises(ValueError):
            import_tenant_bundle(json.dumps(container).encode("utf-8"))

    def test_school_id_mismatch_is_rejected(self):
        school = _school()
        bundle = export_tenant_bundle(school)
        with self.assertRaises(ValueError):
            import_tenant_bundle(bundle, expected_school_id=uuid.uuid4())


class SchoolScopeResolverTests(SimpleTestCase):
    """RLS-mode school-scoping resolver: the O2O fix + the parent-reachable
    relation walk that make the clone complete in single-schema mode.

    These are pure ``_meta`` introspections against the live model graph — no
    DB — so they stay fast and assert invariants rather than brittle exact
    paths (beyond the one direct case every reader knows).
    """

    def test_direct_school_fk_resolves_to_school(self):
        self.assertEqual(_school_lookup_path("people.studentprofile"), "school")

    def test_one_to_one_school_link_is_detected(self):
        # Regression for the O2O bug: a OneToOneField to School used to be
        # skipped by the many_to_one-only check, dropping per-tenant config
        # (RiskThresholds / TenantPaymentPolicy) from every RLS bundle.
        o2o = [
            m
            for m in _tenant_models()
            for f in m._meta.get_fields()
            if getattr(f, "one_to_one", False)
            and getattr(f, "concrete", False)
            and f.name == "school"
            and f.related_model is School
        ]
        self.assertTrue(o2o, "expected >=1 tenant model with a OneToOne school link")
        for m in o2o:
            self.assertEqual(_school_lookup_path(_label(m)), "school", _label(m))

    def test_relation_walk_covers_parent_reachable_models(self):
        # Before the walk, only direct-school-FK models resolved; parent-reachable
        # children (invoice lines, payslips, grade audits, …) were skipped. Assert
        # the walk now covers materially many of them AND every walked path is real.
        direct = walked = 0
        for m in _tenant_models():
            path = _school_lookup_path(_label(m))
            if path is None:
                continue
            if path == "school":
                direct += 1
                continue
            walked += 1
            self.assertTrue(path.endswith("__school"), (_label(m), path))
            model = m
            for seg in path.split("__")[:-1]:
                model = model._meta.get_field(seg).related_model
                self.assertIsNotNone(model, (_label(m), path, seg))
        self.assertGreater(direct, 100, "direct-school-FK models must still resolve")
        self.assertGreater(walked, 20, "relation walk must cover parent-reachable models")

    def test_scope_queryset_rls_returns_qs_for_parent_reachable(self):
        target = next(
            (
                m
                for m in _tenant_models()
                if _direct_school_field(m) is None and _school_lookup_path(_label(m))
            ),
            None,
        )
        self.assertIsNotNone(target, "expected a parent-reachable tenant model")
        qs = _scope_queryset(target, School(id=uuid.uuid4()), schema_mode=False)
        self.assertIsInstance(qs, QuerySet)  # previously this returned None

    def test_scope_queryset_rls_none_when_no_school_linkage(self):
        # Genuinely unscopeable rows (no school linkage at all) still return None
        # — never a cross-tenant leak, never a wrong scope.
        target = next(
            (m for m in _tenant_models() if _school_lookup_path(_label(m)) is None),
            None,
        )
        if target is not None:
            self.assertIsNone(
                _scope_queryset(target, School(id=uuid.uuid4()), schema_mode=False)
            )
