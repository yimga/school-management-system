"""Tests for apps.platform_runtime.action_engine."""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.platform_runtime.action_engine import (
    get_actions_for_user,
    get_control_plane_actions,
    infer_primary_audience,
    serialize_actions,
)
from apps.schools.models import School


class ActionEngineTests(TestCase):
    def test_no_user_returns_empty(self):
        school = School.objects.create(
            name="AE School", slug="ae-school", subdomain="ae-s", is_active=True
        )
        self.assertEqual(get_actions_for_user(None, school), [])

    def test_infer_primary_audience_teacher(self):
        user = User.objects.create_user(
            username="ae_teacher",
            password="x",
            role=User.Role.TEACHER,
        )
        self.assertEqual(infer_primary_audience(user), "teacher")

    def test_infer_primary_audience_parent(self):
        user = User.objects.create_user(
            username="ae_parent",
            password="x",
            role=User.Role.PARENT,
        )
        self.assertEqual(infer_primary_audience(user), "parent")

    def test_teacher_actions_are_bounded_and_serializable(self):
        school = School.objects.create(
            name="AE T", slug="ae-t", subdomain="ae-t", is_active=True
        )
        user = User.objects.create_user(
            username="ae_t2",
            password="x",
            role=User.Role.TEACHER,
        )
        user.is_staff = False
        user.save(update_fields=["is_staff"])
        actions = get_actions_for_user(user, school, limit=8)
        self.assertLessEqual(len(actions), 8)
        payload = serialize_actions(actions)
        self.assertEqual(len(payload), len(actions))
        for row in payload:
            self.assertIn("title", row)
            self.assertIn("action_url", row)
            self.assertTrue(row["action_url"])

    def test_control_plane_strip_for_staff(self):
        user = User.objects.create_user(
            username="ae_cp",
            password="x",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        actions = get_control_plane_actions(user, limit=4)
        self.assertTrue(actions)
        urls = {a.action_url for a in actions}
        self.assertTrue(all(urls))

    def test_no_school_non_super_path_returns_empty(self):
        from django.test import RequestFactory

        user = User.objects.create_user(
            username="ae_path",
            password="x",
            role=User.Role.TEACHER,
        )
        rf = RequestFactory()
        req = rf.get("/portal/teacher/")
        req.user = user
        req.school = None
        self.assertEqual(get_actions_for_user(user, None, request=req), [])

    def test_request_provides_school_when_omitted(self):
        school = School.objects.create(
            name="AE Req", slug="ae-req", subdomain="ae-req", is_active=True
        )
        user = User.objects.create_user(
            username="ae_req_u",
            password="x",
            role=User.Role.TEACHER,
        )

        sch = school
        usr = user

        class Req:
            school = sch
            user = usr

        actions = get_actions_for_user(user, None, request=Req(), limit=8)
        self.assertIsInstance(actions, list)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=False)
    def test_ai_registry_wires_to_actions_with_urls(self):
        """ai_recommendation_registry entries must map to real SystemActions (no dead hrefs)."""
        school = School.objects.create(
            name="AI act", slug="ai-act", subdomain="ai-act", is_active=True
        )
        admin = User.objects.create_user(
            username="ae_ai_admin",
            password="x",
            role=User.Role.ADMIN,
        )
        admin.is_staff = True
        admin.save(update_fields=["is_staff"])
        actions = get_actions_for_user(admin, school, limit=24)
        ser = serialize_actions(actions)
        ai_rows = [r for r in ser if (r.get("recommendation_key") or "").strip()]
        self.assertTrue(
            ai_rows,
            "expected AI registry to contribute at least one action for operator",
        )
        for r in ai_rows:
            self.assertIn("action_url", r)
            self.assertTrue(r["action_url"])
            self.assertTrue(
                r["action_url"].startswith(("/", "http")),
                r["action_url"],
            )
            self.assertIn("source", r)
            self.assertTrue(str(r["source"]).startswith("ai_registry:"))

        teacher = User.objects.create_user(
            username="ae_ai_teacher",
            password="x",
            role=User.Role.TEACHER,
        )
        teacher.is_staff = False
        teacher.save(update_fields=["is_staff"])
        tser = serialize_actions(
            get_actions_for_user(teacher, school, limit=24)
        )
        t_ai = [r for r in tser if (r.get("recommendation_key") or "").strip()]
        self.assertTrue(t_ai, "expected AI actions for teacher audience")
        for r in t_ai:
            self.assertTrue(r.get("action_url"))

    def test_student_user_gets_at_least_one_action(self):
        school = School.objects.create(
            name="AE Stu", slug="ae-stu", subdomain="ae-stu", is_active=True
        )
        user = User.objects.create_user(
            username="ae_student",
            password="x",
            role=User.Role.STUDENT,
        )
        actions = get_actions_for_user(user, school, limit=6)
        self.assertGreaterEqual(len(actions), 1, "student bucket must never be a dead-end")
        for a in actions:
            self.assertTrue((a.action_url or "").strip())

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_single_action_enforcement_returns_at_most_one(self):
        school = School.objects.create(
            name="AE One",
            slug="ae-one",
            subdomain="ae-one",
            is_active=True,
        )
        admin = User.objects.create_user(
            username="ae_one_act",
            password="x",
            role=User.Role.ADMIN,
        )
        admin.is_staff = True
        admin.save(update_fields=["is_staff"])
        actions = get_actions_for_user(admin, school, limit=24)
        self.assertLessEqual(len(actions), 1)
        if actions:
            self.assertTrue(actions[0].action_url)
