"""Wave 15: substitutes / cover ops module."""

import uuid
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.people.models import TeacherProfile
from apps.schoolops.models import SubstituteCover
from apps.schoolops.substitute_handover import SubstituteBroadcastResult
from apps.schoolops.views_tenant_ops import ops_substitutes
from apps.schools.models import School

User = get_user_model()


class TenantOpsWave15SubstitutesTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Sub School",
            slug=f"sub-{uuid.uuid4().hex[:10]}",
            subdomain=f"sub-{uuid.uuid4().hex[:10]}",
            features={"substitutes": True},
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="adm@t.test",
            password="x",
            role=User.Role.ADMIN,
        )
        self.t1 = User.objects.create_user(
            username=f"t1-{uuid.uuid4().hex[:8]}",
            email="t1@t.test",
            password="x",
            role=User.Role.TEACHER,
            first_name="Ann",
            last_name="Absent",
        )
        self.t2 = User.objects.create_user(
            username=f"t2-{uuid.uuid4().hex[:8]}",
            email="t2@t.test",
            password="x",
            role=User.Role.TEACHER,
            first_name="Bob",
            last_name="Cover",
        )
        TeacherProfile.objects.create(user=self.t1, school=self.school)
        TeacherProfile.objects.create(user=self.t2, school=self.school, phone="+15550002")

    def _req(self, method, path, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = self.admin
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_record_substitute_cover(self):
        r = ops_substitutes(
            self._req(
                "POST",
                "/sub/",
                {
                    "work_date": "2026-03-15",
                    "absent_teacher_id": str(self.t1.id),
                    "covering_teacher_id": str(self.t2.id),
                    "period_label": "P3",
                    "notes": "Math",
                },
            )
        )
        self.assertEqual(r.status_code, 302)
        sc = SubstituteCover.objects.get(school=self.school)
        self.assertEqual(sc.work_date, date(2026, 3, 15))
        self.assertEqual(sc.absent_teacher_id, self.t1.id)
        self.assertEqual(sc.covering_teacher_id, self.t2.id)

    def test_substitutes_feature_off_403(self):
        self.school.features = {"substitutes": False}
        self.school.save(update_fields=["features"])
        resp = ops_substitutes(self._req("GET", "/sub/"))
        self.assertEqual(resp.status_code, 403)

    @patch("apps.schoolops.substitute_handover.broadcast_substitute_request")
    def test_broadcast_uses_ranked_candidate_service(self, broadcast):
        broadcast.return_value = [
            SubstituteBroadcastResult(
                candidate_id=str(self.t2.id),
                channel="sms",
                accepted=True,
            )
        ]
        with self.settings(RMC_AUTO_ENQUEUE_OUTBOUND=False):
            response = ops_substitutes(
                self._req(
                    "POST",
                    "/sub/",
                    {
                        "action": "broadcast",
                        "work_date": "2026-06-09",
                        "absent_teacher_id": str(self.t1.id),
                        "period_label": "P3",
                    },
                )
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ranked candidates contacted")
        self.assertEqual(SubstituteCover.objects.count(), 0)
        broadcast.assert_called_once()

    def test_open_market_and_teacher_claim(self):
        from apps.schoolops.substitute_market import list_open_shifts

        open_resp = ops_substitutes(
            self._req(
                "POST",
                "/sub/",
                {
                    "action": "open_market",
                    "work_date": "2026-06-10",
                    "absent_teacher_id": str(self.t1.id),
                    "period_label": "P2",
                },
            )
        )
        self.assertEqual(open_resp.status_code, 302)
        open_rows = list_open_shifts(school_id=int(self.school.pk))
        self.assertEqual(len(open_rows), 1)
        shift_id = open_rows[0]["shift_id"]

        teacher_req = self._req(
            "POST",
            "/sub/",
            {"action": "claim_market", "shift_id": shift_id},
        )
        teacher_req.user = self.t2
        claim_resp = ops_substitutes(teacher_req)
        self.assertEqual(claim_resp.status_code, 302)
        cover = SubstituteCover.objects.get(school=self.school)
        self.assertEqual(cover.absent_teacher_id, self.t1.id)
        self.assertEqual(cover.covering_teacher_id, self.t2.id)

    def test_open_market_auto_notifies_ranked_candidates(self):
        """Metric 12 view path: open_market fans out SMS/WhatsApp (not mocked broadcast)."""
        wa_calls = []

        def fake_wa(school, phone, body="", idempotency_key=""):
            wa_calls.append({"phone": phone, "body": body})
            return True

        with patch(
            "apps.communication.notification_service.send_whatsapp",
            side_effect=fake_wa,
        ), patch(
            "apps.communication.notification_service.send_sms",
            return_value=False,
        ), self.settings(RMC_AUTO_ENQUEUE_OUTBOUND=False):
            response = ops_substitutes(
                self._req(
                    "POST",
                    "/sub/",
                    {
                        "action": "open_market",
                        "work_date": "2026-06-11",
                        "absent_teacher_id": str(self.t1.id),
                        "period_label": "P4",
                    },
                )
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(wa_calls), 1)
        self.assertEqual(wa_calls[0]["phone"], "+15550002")
        self.assertIn("P4", wa_calls[0]["body"])

    def test_teacher_can_view_open_shifts_without_ops_role(self):
        self.t2.role = User.Role.TEACHER
        self.t2.save(update_fields=["role"])
        req = self._req("GET", "/sub/")
        req.user = self.t2
        resp = ops_substitutes(req)
        self.assertEqual(resp.status_code, 200)
