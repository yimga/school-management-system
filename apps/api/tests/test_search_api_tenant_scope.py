from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import Subject
from apps.api.search_api import GlobalSearchAPI
from apps.schools.models import School


class SearchApiTenantScopeTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="School A",
            slug="school-a",
            subdomain="school-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="School B",
            slug="school-b",
            subdomain="school-b",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="search-admin",
            password="x",
            role=User.Role.ADMIN,
        )
        self.search_api = GlobalSearchAPI()
        Subject.objects.create(
            school=self.school_a, name="Mathematics", category=Subject.Category.GENERAL
        )
        Subject.objects.create(
            school=self.school_b, name="Mathematics", category=Subject.Category.GENERAL
        )

    def test_subject_search_is_tenant_scoped(self):
        results = self.search_api._search_type(
            self.search_api.SEARCH_CONFIG["subject"],
            query="Math",
            limit=10,
            user=self.user,
            school=self.school_a,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Mathematics")
