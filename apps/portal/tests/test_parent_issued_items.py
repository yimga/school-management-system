"""#14 Inventory — parent issued-items surface after student checkout."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.academics.models import AcademicYear
from apps.people.models import StudentGuardian, StudentProfile, StudentResourceReturn
from apps.schoolops.inventory_services import checkout_inventory
from apps.schoolops.models import InventoryItem
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ParentIssuedItemsTests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Iss {tag}",
            slug=f"iss-{tag}",
            subdomain=f"iss-{tag}",
            is_active=True,
            features={"inventory": True},
        )
        self.year = AcademicYear.objects.create(
            name="Y1",
            start_date="2025-01-01",
            end_date="2025-12-31",
            school=self.school,
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            first_name="Kid",
            last_name="One",
            date_of_birth="2013-01-01",
            student_code=f"K{tag}",
            school=self.school,
            academic_year=self.year,
        )
        self.parent = User.objects.create_user(
            username=f"par-{tag}",
            email=f"par-{tag}@t.test",
            password="Test1234!",
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.create(
            user=self.parent, school=self.school, role="PARENT"
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
            can_view_results=True,
        )
        self.item = InventoryItem.objects.create(
            school=self.school, name="Chromebook", quantity=5, location="Lab"
        )
        self.client = Client()

    def test_parent_sees_outstanding_issued_item(self):
        checkout_inventory(
            school=self.school,
            item=self.item,
            quantity=1,
            student=self.student,
            academic_year=self.year,
        )
        self.assertTrue(
            StudentResourceReturn.objects.filter(
                student=self.student, item_label="Chromebook", returned_at__isnull=True
            ).exists()
        )
        self.client.force_login(self.parent)
        session = self.client.session
        session["school_id"] = str(self.school.id)
        session.save()
        resp = self.client.get(reverse("portal:parent_issued_items"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Chromebook")
        self.assertContains(resp, "Kid")
