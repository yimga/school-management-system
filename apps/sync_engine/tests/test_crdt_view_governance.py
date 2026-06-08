import json

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.schools.models import School
from apps.sync_engine.views_crdt import CRDTOpsApplyView


class CRDTOpsApplyGovernanceTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="crdt-user", password="x")
        self.school = School.objects.create(
            name="CRDT School",
            slug="crdt-school",
            subdomain="crdt-school",
        )

    def _post(self, ops, *, school=None, device_id="device-a"):
        request = self.factory.post(
            "/api/v1/crdt/apply/",
            data=json.dumps({"ops": ops, "device_id": device_id}),
            content_type="application/json",
        )
        request.user = self.user
        request.tenant = school or self.school
        return CRDTOpsApplyView().post(request)

    def test_approved_lww_is_actor_bound_and_persisted(self):
        response = self._post(
            [
                {
                    "kind": "LWW",
                    "entity": "student_note",
                    "key": "student_note:draft-1",
                    "value": "local draft",
                    "hlc": "100:0:spoofed-actor",
                }
            ]
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body["applied"], 1)
        self.school.refresh_from_db()
        stored = self.school.settings["crdt_state"]
        self.assertEqual(stored["policy_version"], body["policy_version"])
        self.assertTrue(
            stored["lww"]["student_note:draft-1"]["hlc"].endswith(
                f":u{self.user.pk}:device-a"
            )
        )

    def test_protected_grade_lww_is_rejected(self):
        response = self._post(
            [
                {
                    "kind": "LWW",
                    "entity": "grade_entry",
                    "key": "grade_entry:1",
                    "value": 20,
                    "hlc": "100:0:device",
                }
            ]
        )
        body = json.loads(response.content)
        self.assertEqual(body["applied"], 0)
        self.assertIn("crdt_kind_not_allowed", body["rejected"][0]["reason"])

    def test_attendance_uses_canonical_replay_not_generic_crdt_state(self):
        response = self._post(
            [
                {
                    "kind": "LWW",
                    "entity": "attendance_record",
                    "key": "attendance_record:student-1:2026-06-08",
                    "value": "present",
                    "hlc": "100:0:device",
                }
            ]
        )
        body = json.loads(response.content)
        self.assertEqual(body["applied"], 0)
        self.assertIn("crdt_kind_not_allowed", body["rejected"][0]["reason"])

    def test_key_must_be_in_entity_namespace(self):
        response = self._post(
            [
                {
                    "kind": "LWW",
                    "entity": "student_note",
                    "key": "permission_grant:admin",
                    "value": True,
                    "hlc": "100:0:device",
                }
            ]
        )
        body = json.loads(response.content)
        self.assertEqual(body["applied"], 0)
        self.assertIn("crdt_key_must_start_with", body["rejected"][0]["reason"])

    def test_gcounter_retry_is_idempotent(self):
        op = {
            "kind": "GCOUNTER",
            "entity": "telemetry_counter",
            "counter_key": "telemetry_counter:offline-captures",
            "actor_id": "spoofed",
            "value": 5,
        }
        first = json.loads(self._post([op]).content)
        second = json.loads(self._post([op]).content)
        self.assertEqual(first["materialized"]["gcounter"].popitem()[1], 5)
        self.assertEqual(second["materialized"]["gcounter"].popitem()[1], 5)

    def test_orset_remove_before_add_converges(self):
        response = self._post(
            [
                {
                    "kind": "ORSET-REMOVE",
                    "entity": "lesson_plan_tags",
                    "set_key": "lesson_plan_tags:plan-1",
                    "element": "exam",
                    "tag": "",
                    "observed_tags": ["tag-1"],
                },
                {
                    "kind": "ORSET-ADD",
                    "entity": "lesson_plan_tags",
                    "set_key": "lesson_plan_tags:plan-1",
                    "element": "exam",
                    "tag": "tag-1",
                    "observed_tags": [],
                },
            ]
        )
        body = json.loads(response.content)
        self.assertEqual(body["applied"], 2)
        self.assertEqual(
            body["materialized"]["orset"]["lesson_plan_tags:plan-1"],
            [],
        )

    def test_tenant_state_is_isolated(self):
        other = School.objects.create(
            name="Other CRDT School",
            slug="other-crdt-school",
            subdomain="other-crdt-school",
        )
        self._post(
            [
                {
                    "kind": "LWW",
                    "entity": "lesson_plan",
                    "key": "lesson_plan:draft-1",
                    "value": "tenant one",
                    "hlc": "100:0:device",
                }
            ]
        )
        other.refresh_from_db()
        self.assertNotIn("crdt_state", other.settings)
