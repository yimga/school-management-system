"""FK referent enrichment — specialty edits must ship their department parent."""

from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import Department, Specialty
from apps.accounts.models import User
from apps.api.sync_services import enrich_delta_rows_with_fk_referents, _get_entity_config
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import export_delta_bundle, verify_and_parse_bundle
from apps.sync_engine.edge_inbox import apply_pulled_bundle
from apps.sync_engine.edge_outbox import build_edge_delta_rows

_SIGN_KEY = "edge-fk-referent-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class FkReferentEnrichmentTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"FK {uid}", slug=f"fk-{uid}", subdomain=f"fk{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"fk_admin_{uid}", password="Test1234", email=f"f{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.dept = Department(
            school=self.school, name="Sciences", code=f"SCI{uid[:4]}"
        )
        self.dept.pk = 9000 + int(uid[:4], 16) % 1000
        self.dept.save(force_insert=True)
        self.spec = Specialty.objects.create(
            school=self.school,
            department=self.dept,
            name="Pure Science",
            code=f"PS{uid[:5]}",
        )

    def test_enrichment_adds_unchanged_department_when_specialty_changes(self):
        Specialty.objects.filter(pk=self.spec.pk).update(
            name="Pure Science (cloud edit)",
            updated_at=timezone.now(),
        )
        rows, _meta = build_edge_delta_rows(
            self.school, since=timezone.now() - timezone.timedelta(minutes=5)
        )
        entity_types = {r["entity_type"] for r in rows}
        self.assertIn("specialty", entity_types)
        self.assertIn("department", entity_types)

    def test_box_without_department_applies_specialty_after_enriched_pull(self):
        dept_pk = self.dept.pk
        spec_pk = self.spec.pk
        config = _get_entity_config(include_derived=True)
        rows = [
            {
                "entity_type": "department",
                "id": dept_pk,
                "client_offline_id": "",
                "changes": {
                    "name": self.dept.name,
                    "code": self.dept.code,
                },
                "updated_at": timezone.now().isoformat(),
            },
            {
                "entity_type": "specialty",
                "id": spec_pk,
                "client_offline_id": "",
                "changes": {
                    "name": "Pure Science (synced)",
                    "code": self.spec.code,
                    "department_id": dept_pk,
                },
                "updated_at": timezone.now().isoformat(),
            },
        ]
        enriched = enrich_delta_rows_with_fk_referents(rows, self.school, config)
        self.assertTrue(any(r["entity_type"] == "department" for r in enriched))

        # Model a box that never received these rows. A normal local delete now creates a
        # tombstone, which correctly wins over an older pull; that is a different state
        # from an absent-on-clone row and would turn this fixture into a delete-dominance
        # test. Suppress propagation only while constructing the empty-box state.
        with override_settings(RMC_SYNC_DELETE_PROPAGATION_ENABLED=False):
            Specialty.objects.filter(pk=spec_pk).delete()
            Department.objects.filter(pk=dept_pk).delete()

        bundle = export_delta_bundle(
            school_id=str(self.school.id), rows=enriched, device_id="test"
        )
        result = apply_pulled_bundle(self.school, self.user, bundle, origin="cloud-pull")
        self.assertTrue(result["ok"], result)
        self.assertTrue(
            Department.objects.filter(pk=dept_pk, school=self.school).exists(), result
        )
        spec = Specialty.objects.get(pk=spec_pk)
        self.assertEqual(spec.department_id, dept_pk)
        self.assertEqual(spec.name, "Pure Science (synced)")
