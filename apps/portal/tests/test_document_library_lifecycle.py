from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.packages.models import DocumentPack
from apps.portal.models import PortalFeatureItem


class DocumentLibraryLifecycleTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="doc-admin",
            email="doc-admin@example.com",
            password="testpass123",
        )
        self.parent = User.objects.create_user(
            username="doc-parent",
            email="doc-parent@example.com",
            password="testpass123",
            role=User.Role.PARENT,
        )
        self.pack = DocumentPack.objects.create(
            code="enrollment-pack",
            name="Enrollment Pack",
            lifecycle_states=["draft", "review", "approved", "archived"],
            retention_rule={"archive_after_days": 30},
            is_active=True,
        )

    def test_document_save_builds_search_index_and_retention(self):
        document = PortalFeatureItem.objects.create(
            feature=PortalFeatureItem.Feature.DOCUMENTS,
            title="Enrollment Policy 2026",
            description="Policy for registration and admissions.",
            link="https://example.com/enrollment-policy",
            document_type=PortalFeatureItem.DocumentType.POLICY,
            document_pack=self.pack,
            lifecycle_state="approved",
            created_by=self.superuser,
            visible_to_roles=["PARENT"],
            is_active=True,
        )

        self.assertIn("enrollment pack", document.search_index)
        self.assertIn("approved", document.search_index)
        self.assertIsNotNone(document.published_at)
        self.assertIsNotNone(document.retention_review_at)

    def test_document_can_view_respects_lifecycle(self):
        draft_doc = PortalFeatureItem.objects.create(
            feature=PortalFeatureItem.Feature.DOCUMENTS,
            title="Draft Form",
            link="https://example.com/draft-form",
            document_type=PortalFeatureItem.DocumentType.FORM,
            document_pack=self.pack,
            lifecycle_state="draft",
            created_by=self.superuser,
            visible_to_roles=["PARENT"],
            is_active=True,
        )
        approved_doc = PortalFeatureItem.objects.create(
            feature=PortalFeatureItem.Feature.DOCUMENTS,
            title="Approved Handbook",
            link="https://example.com/approved-handbook",
            document_type=PortalFeatureItem.DocumentType.HANDBOOK,
            document_pack=self.pack,
            lifecycle_state="approved",
            created_by=self.superuser,
            visible_to_roles=["PARENT"],
            is_active=True,
        )

        self.assertFalse(draft_doc.can_view(self.parent))
        self.assertTrue(draft_doc.can_view(self.superuser))
        self.assertTrue(approved_doc.can_view(self.parent))

    def test_document_library_manage_filters_by_pack_lifecycle_and_search(self):
        PortalFeatureItem.objects.create(
            feature=PortalFeatureItem.Feature.DOCUMENTS,
            title="Enrollment Checklist",
            description="Review checklist for admissions.",
            link="https://example.com/enrollment-checklist",
            document_type=PortalFeatureItem.DocumentType.GENERAL,
            document_pack=self.pack,
            lifecycle_state="approved",
            created_by=self.superuser,
            is_active=True,
        )
        PortalFeatureItem.objects.create(
            feature=PortalFeatureItem.Feature.DOCUMENTS,
            title="Archived Memo",
            link="https://example.com/archived-memo",
            document_type=PortalFeatureItem.DocumentType.OTHER,
            document_pack=self.pack,
            lifecycle_state="archived",
            created_by=self.superuser,
            is_active=False,
        )

        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("portal:document_library_manage"),
            {
                "embed": "1",
                "pack": self.pack.code,
                "lifecycle": "approved",
                "q": "checklist",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enrollment Checklist")
        self.assertNotContains(response, "Archived Memo")
        self.assertContains(response, "Enrollment Pack")
