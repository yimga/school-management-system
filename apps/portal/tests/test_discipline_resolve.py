"""Producer-path proof for Incident RESOLVED (metric 11).

HEAD ships NO product path that transitions an ``Incident`` to ``RESOLVED``: the
routing FSM only ever writes ``REFERRED`` (``discipline_services.py``) and the
incident API hardcodes ``REFERRED`` on create (``views_discipline_api.py``). The
caseload consumer keeps a student while ``open_count`` (= incidents whose status is
not ``RESOLVED``) is > 0, so a student with an open incident stays on the MTSS
counselor caseload forever.

These tests drive the REAL resolve producer (the ``resolve_incident`` FSM service and
the JSON resolve endpoint) — never a direct ORM ``status=RESOLVED`` fixture (the
false-green the legacy caseload test relies on) — and assert the caseload clears via
that path and that RBAC holds (a teacher who can REFER cannot resolve).
"""

import json
import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.academics.discipline_services import resolve_incident
from apps.academics.models import Incident
from apps.academics.models_discipline import RestorativeAction
from apps.academics.views_discipline_api import api_discipline_incident_resolve
from apps.accounts.models import Permission
from apps.people.models import StudentProfile
from apps.portal.views_teacher import counselor_caseload
from apps.schools.models import School

User = get_user_model()


def _school(tag):
    return School.objects.create(
        name=f"Discipline {tag}",
        slug=f"disc-{tag}-{uuid.uuid4().hex[:8]}",
        subdomain=f"disc-{tag}-{uuid.uuid4().hex[:8]}",
    )


def _student(school, first, last):
    return StudentProfile.objects.create(
        school=school,
        first_name=first,
        last_name=last,
        student_code=f"ST-{uuid.uuid4().hex[:6]}",
    )


@override_settings(ROOT_URLCONF="config.tenant_urls")
class DisciplineResolveProducerTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = _school("A")

        # On the caseload ONLY via open_count: Tier 1, stale (older than the 30-day
        # recency window), severity LOW (so the routing signal creates no restorative
        # action / escalation), status defaults to OPEN. Resolving removes the sole
        # inclusion criterion -> the student leaves the caseload entirely.
        self.stu = _student(self.school, "Grover", "Marchbanks")
        self.incident = Incident.objects.create(
            school=self.school,
            student=self.stu,
            incident_type=Incident.Type.BEHAVIOR,
            severity=Incident.Severity.LOW,
            mtss_tier=Incident.MtssTier.TIER_1,
            date=date.today() - timedelta(days=60),
            notify_parent=False,
        )
        # Guard the domain premise: creation must NOT already be resolved.
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.OPEN)

        # Counselor: TEACHER role; ONLY the granted discipline.manage code opens the gate.
        self.counselor = User.objects.create_user(
            username=f"couns-{uuid.uuid4().hex[:8]}",
            email="c@resolve.test",
            password="x",
            role=User.Role.TEACHER,
        )
        perm, _ = Permission.objects.get_or_create(
            code="discipline.manage",
            defaults={"name": "Discipline management"},
        )
        self.counselor.feature_permissions.add(perm)

        # Teacher: role TEACHER can REFER (create incidents) but holds NO
        # discipline.manage -> must NOT be able to resolve.
        self.teacher = User.objects.create_user(
            username=f"tch-{uuid.uuid4().hex[:8]}",
            email="t@resolve.test",
            password="x",
            role=User.Role.TEACHER,
        )

    def _wrap(self, r, user):
        r.user = user
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def _get_caseload(self, user):
        return self._wrap(self.factory.get("/staff/discipline/caseload/"), user)

    def _post_resolve(self, user):
        return self._wrap(
            self.factory.post(
                f"/api/discipline/incidents/{self.incident.pk}/resolve/"
            ),
            user,
        )

    def test_student_on_caseload_before_resolve(self):
        resp = counselor_caseload(self._get_caseload(self.counselor))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Marchbanks", resp.content.decode())

    def test_resolve_via_api_clears_caseload(self):
        # Drive the REAL product path: the JSON resolve endpoint.
        resp = api_discipline_incident_resolve(
            self._post_resolve(self.counselor), incident_id=self.incident.pk
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], Incident.Status.RESOLVED)

        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.RESOLVED)
        self.assertIsNotNone(self.incident.resolved_at)
        self.assertEqual(self.incident.resolved_by_id, self.counselor.pk)

        # The caseload consumer's open_count now drops to 0; with no tier-2/3 and no
        # recent incident, the student leaves the caseload.
        resp2 = counselor_caseload(self._get_caseload(self.counselor))
        self.assertEqual(resp2.status_code, 200)
        self.assertNotIn("Marchbanks", resp2.content.decode())

    def test_teacher_who_can_refer_cannot_resolve(self):
        resp = api_discipline_incident_resolve(
            self._post_resolve(self.teacher), incident_id=self.incident.pk
        )
        self.assertEqual(resp.status_code, 403)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.OPEN)

    def test_resolve_completes_open_restorative_actions(self):
        ra = RestorativeAction.objects.create(
            school=self.school,
            incident=self.incident,
            title="Restorative conference",
            status=RestorativeAction.Status.PLANNED,
        )
        result = resolve_incident(incident=self.incident, resolved_by=self.counselor)
        self.assertTrue(result["resolved"])
        self.assertEqual(result["restorative_completed"], 1)
        ra.refresh_from_db()
        self.assertEqual(ra.status, RestorativeAction.Status.COMPLETED)
        self.assertIsNotNone(ra.completed_at)

    def test_resolve_is_idempotent(self):
        first = resolve_incident(incident=self.incident, resolved_by=self.counselor)
        self.assertTrue(first["resolved"])
        self.incident.refresh_from_db()
        again = resolve_incident(incident=self.incident, resolved_by=self.counselor)
        self.assertFalse(again["resolved"])
        self.assertTrue(again["already_resolved"])
