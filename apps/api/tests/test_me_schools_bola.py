"""BOLA: GET /api/v1/me/schools must not leak foreign tenant ids."""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.api.views_v1 import MeSchoolsView
from apps.schools.models import School, SchoolMembership


class MeSchoolsBOLATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school_a = School.objects.create(
            name=f"Me Schools A {uid}",
            slug=f"msa-{uid}",
            subdomain=f"msa{uid}",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name=f"Me Schools B {uid}",
            slug=f"msb-{uid}",
            subdomain=f"msb{uid}",
            is_active=True,
        )
        User = get_user_model()
        cls.user_a = User.objects.create_user(
            username=f"user_a_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=cls.user_a, school=cls.school_a, role="ADMIN", is_primary=True
        )

    def _get_me_schools(self, user, school=None):
        rf = RequestFactory()
        req = rf.get("/api/v1/me/schools")
        req.user = user
        if school is not None:
            req.school = school
        return MeSchoolsView.as_view()(req)

    def test_me_schools_excludes_foreign_school(self):
        resp = self._get_me_schools(self.user_a, school=self.school_a)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        ids = {row["school_id"] for row in data.get("schools", [])}
        ids.update(row["school_id"] for row in data.get("child_schools", []))
        self.assertIn(str(self.school_a.pk), ids)
        self.assertNotIn(str(self.school_b.pk), ids)

    def test_me_schools_child_hierarchy_included_when_parent_member(self):
        child = School.objects.create(
            name="Child campus",
            slug=f"child-{uuid.uuid4().hex[:6]}",
            subdomain=f"child{uuid.uuid4().hex[:6]}",
            parent_school=self.school_a,
            is_active=True,
        )
        resp = self._get_me_schools(self.user_a, school=self.school_a)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        child_ids = {row["school_id"] for row in data.get("child_schools", [])}
        self.assertIn(str(child.pk), child_ids)
