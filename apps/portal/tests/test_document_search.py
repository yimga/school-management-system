"""Google pillar: portal document library search helper."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.portal.document_lifecycle import build_document_search_index
from apps.portal.document_search import filter_documents_by_search
from apps.portal.models import PortalFeatureItem
from apps.schools.models import School


class DocumentSearchTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(
            name="Doc Search School",
            slug="doc-search",
            subdomain="doc-search",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="doc_search_admin",
            password="Test1234",
            role="ADMIN",
        )
        self.doc = PortalFeatureItem.objects.create(
            school=self.school,
            title="Enrollment Handbook",
            description="Policies for new students",
            feature=PortalFeatureItem.Feature.DOCUMENTS,
            link="https://example.com/handbook",
            created_by=self.user,
        )
        self.doc.search_index = build_document_search_index(self.doc)
        self.doc.save(update_fields=["search_index"])

    def test_filter_finds_by_title_token(self):
        qs = PortalFeatureItem.objects.filter(school=self.school)
        found = list(filter_documents_by_search(qs, "enrollment"))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].pk, self.doc.pk)

    def test_short_query_is_noop(self):
        qs = PortalFeatureItem.objects.filter(school=self.school)
        self.assertEqual(list(filter_documents_by_search(qs, "a")), list(qs))
