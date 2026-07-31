"""Full-fidelity tenant portability — export/import round-trip + fail-closed checks."""
import json
import uuid

from django.test import TestCase

from apps.lifecycle.tenant_portability import export_tenant_bundle, import_tenant_bundle
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
