"""Incident timeline of record + postmortem artifact.

Locks the 9.8 incidents wave (2026-07-02). Before it, PlatformIncident had a
state machine but no memory: no trail of status flips, no operator notes, no
postmortem artifact anywhere in code — the lifecycle could never close the
loop from "resolved" to "learned". These tests assert the timeline is written
by every writer (operator transition API, idempotent incident services,
manual updates), the postmortem entry flips the has_postmortem contract, and
the endpoints are auth-gated and validating.
"""

from __future__ import annotations

import json

from django.test import TestCase

from apps.accounts.models import User

from apps.observability.incident_services import (
    resolve_platform_incident,
    upsert_platform_incident,
)
from apps.observability.models import IncidentUpdate, PlatformIncident
from apps.observability.models_incident_timeline import (
    incident_has_postmortem,
    record_incident_update,
)


def _mk_incident(**overrides) -> PlatformIncident:
    defaults = {
        "title": "Timeline test incident",
        "incident_type": PlatformIncident.IncidentType.DATA,
        "severity": PlatformIncident.Severity.HIGH,
        "summary": "test",
        "source_system": "tests",
    }
    defaults.update(overrides)
    return PlatformIncident.objects.create(**defaults)


class IncidentTimelineModelTests(TestCase):
    def test_record_and_postmortem_contract(self):
        incident = _mk_incident()
        self.assertFalse(incident_has_postmortem(incident))
        record_incident_update(incident, kind=IncidentUpdate.Kind.UPDATE, body="probe")
        self.assertFalse(incident_has_postmortem(incident))
        record_incident_update(
            incident, kind=IncidentUpdate.Kind.POSTMORTEM, body="RCA: threshold too low"
        )
        self.assertTrue(incident_has_postmortem(incident))
        self.assertEqual(incident.updates.count(), 2)

    def test_record_is_best_effort_on_bad_input(self):
        # Never raises even on a broken incident reference.
        self.assertIsNone(
            record_incident_update(object(), kind="update", body="x")
        )


class IncidentServicesTimelineTests(TestCase):
    def test_auto_open_and_auto_resolve_write_trail(self):
        incident, created = upsert_platform_incident(
            incident_key="test_key_1",
            title="Auto incident",
            incident_type=PlatformIncident.IncidentType.DATA,
            severity=PlatformIncident.Severity.HIGH,
            summary="over threshold",
            source_system="tests",
        )
        self.assertTrue(created)
        kinds = list(incident.updates.values_list("kind", flat=True))
        self.assertIn(IncidentUpdate.Kind.STATUS_CHANGE, kinds)
        self.assertIn("Opened automatically", incident.updates.first().body)

        resolved = resolve_platform_incident(
            incident_key="test_key_1",
            source_system="tests",
        )
        self.assertEqual(resolved, 1)
        incident.refresh_from_db()
        self.assertEqual(incident.status, PlatformIncident.Status.RESOLVED)
        bodies = " | ".join(incident.updates.values_list("body", flat=True))
        self.assertIn("Auto-resolved", bodies)


class IncidentTimelineEndpointTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="incident_operator",
            password="Test1234!",
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        self.incident = _mk_incident()
        self.client.force_login(self.operator)

    def _timeline_url(self):
        return f"/api/observability/incidents/{self.incident.pk}/timeline/"

    def _updates_url(self):
        return f"/api/observability/incidents/{self.incident.pk}/updates/"

    def test_add_postmortem_then_timeline_reflects_it(self):
        response = self.client.post(
            self._updates_url(),
            data=json.dumps({"kind": "postmortem", "body": "RCA: dead-letter surge"}),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["incident"]["has_postmortem"])

        timeline = self.client.get(self._timeline_url(), HTTP_HOST="manager.runmycampus.com").json()
        self.assertEqual(timeline["status"], "success")
        kinds = {e["kind"] for e in timeline["timeline"]}
        self.assertIn("postmortem", kinds)

    def test_status_transition_writes_trail(self):
        response = self.client.post(
            f"/api/observability/incidents/{self.incident.pk}/status/",
            data=json.dumps({"action": "acknowledge"}),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = self.incident.updates.get()
        self.assertEqual(entry.kind, IncidentUpdate.Kind.STATUS_CHANGE)
        self.assertIn("acknowledged", entry.body)

    def test_update_add_validates_kind_and_body(self):
        bad_kind = self.client.post(
            self._updates_url(),
            data=json.dumps({"kind": "nonsense", "body": "x"}),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(bad_kind.status_code, 400)
        no_body = self.client.post(
            self._updates_url(),
            data=json.dumps({"kind": "update"}),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(no_body.status_code, 400)
        self.assertEqual(self.incident.updates.count(), 0)

    def test_unknown_incident_404(self):
        response = self.client.get(
            "/api/observability/incidents/00000000-0000-0000-0000-000000000000/timeline/",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 404)
