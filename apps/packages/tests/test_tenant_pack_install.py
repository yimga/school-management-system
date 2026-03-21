"""N20: DocumentPack / ExperiencePack mirrored to InstalledPackage for rollback UI."""

import uuid

from django.test import TestCase

from apps.brand_experience.experience_packs import rollback_experience_pack
from apps.packages.models import DocumentPack, ExperiencePack, InstalledPackage
from apps.packages.tenant_pack_install import (
    record_document_pack_usage,
    sync_experience_pack_install_from_school,
)
from apps.schools.models import School


class TenantPackInstallTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Pack School",
            slug=f"pack-{uuid.uuid4().hex[:8]}",
            subdomain=f"pack-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )

    def test_record_document_pack_creates_installed_row(self):
        pack = DocumentPack.objects.create(
            code="policies-v1",
            name="Policies",
            version="2.1.0",
            lifecycle_states=["draft", "approved"],
        )
        out = record_document_pack_usage(self.school, pack, actor_id=1)
        self.assertTrue(out.get("ok"), out)
        inst = InstalledPackage.objects.get(
            school=self.school, package_id="doc-pack:policies-v1"
        )
        self.assertEqual(inst.package_type, "document_pack")
        self.assertEqual(inst.version, "2.1.0")
        self.assertTrue(inst.is_active)
        out2 = record_document_pack_usage(self.school, pack, actor_id=1)
        self.assertTrue(out2.get("skipped"))

    def test_sync_experience_pack_from_school_settings(self):
        ExperiencePack.objects.create(
            code="exp-n20",
            name="N20 Exp",
            version="1.2.0",
            is_active=True,
        )
        self.school.settings = {"experience_pack_code": "exp-n20"}
        self.school.save(update_fields=["settings"])
        out = sync_experience_pack_install_from_school(self.school, actor_id=2)
        self.assertTrue(out.get("ok"), out)
        inst = InstalledPackage.objects.get(
            school=self.school, package_id="exp-pack:exp-n20"
        )
        self.assertEqual(inst.package_type, "experience_pack")
        self.assertEqual(inst.version, "1.2.0")

    def test_rollback_experience_pack_finds_exp_prefix_row(self):
        ExperiencePack.objects.create(code="exp-x", name="X", version="1.0.0")
        self.school.settings = {"experience_pack_code": "exp-x"}
        self.school.save(update_fields=["settings"])
        InstalledPackage.objects.create(
            package_id="exp-pack:exp-x",
            package_type="experience_pack",
            version="1.0.0",
            school=self.school,
            scope="tenant",
            is_active=True,
        )
        r = rollback_experience_pack(self.school, actor_id=9)
        self.assertTrue(r.get("ok"), r)
        self.assertFalse(
            InstalledPackage.objects.filter(
                school=self.school, package_id="exp-pack:exp-x", is_active=True
            ).exists()
        )
