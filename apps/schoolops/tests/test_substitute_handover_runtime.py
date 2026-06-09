"""Runtime tests for apps.schoolops.substitute_handover (batch 1493)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.schoolops.substitute_handover import (
    SubstituteCandidate,
    SubstituteHandoverError,
    TeacherAbsenceTrigger,
    access_check,
    broadcast_substitute_request,
    build_packet,
    rank_substitute_candidates,
)


def _now() -> datetime:
    return datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc)


class SubstituteHandoverRuntimeTests(SimpleTestCase):
    def _trigger(self, *, duration_hours: int = 4) -> TeacherAbsenceTrigger:
        return TeacherAbsenceTrigger(
            tenant_id="tenant-x",
            teacher_id="teacher-1",
            absence_start=_now(),
            absence_end=_now() + timedelta(hours=duration_hours),
            reason_code="sick",
        )

    def test_build_packet_hashes_all_identities(self) -> None:
        trig = self._trigger()
        packet = build_packet(trigger=trig, substitute_id="sub-1")
        for h in (packet.tenant_id_hash, packet.teacher_id_hash, packet.substitute_id_hash):
            self.assertEqual(len(h), 12)
            self.assertNotIn("tenant-x", h)

    def test_packet_gates_medical_by_default(self) -> None:
        trig = self._trigger()
        packet = build_packet(trigger=trig, substitute_id="sub-1")
        self.assertTrue(packet.medical_iep_gated)

    def test_packet_ungates_medical_when_explicit(self) -> None:
        trig = self._trigger()
        packet = build_packet(
            trigger=trig, substitute_id="sub-1", expose_medical_iep=True
        )
        self.assertFalse(packet.medical_iep_gated)

    def test_access_check_expires_after_window(self) -> None:
        trig = self._trigger(duration_hours=1)
        packet = build_packet(trigger=trig, substitute_id="sub-1", grace_minutes=0)
        in_window = trig.absence_start
        after = trig.absence_end + timedelta(minutes=10)
        self.assertTrue(access_check(packet, now=in_window))
        self.assertFalse(access_check(packet, now=after))

    def test_invalid_window_rejected(self) -> None:
        with self.assertRaises(SubstituteHandoverError):
            TeacherAbsenceTrigger(
                tenant_id="t",
                teacher_id="t1",
                absence_start=_now(),
                absence_end=_now(),
            )

    def test_lesson_outline_normalized(self) -> None:
        trig = self._trigger()
        packet = build_packet(
            trigger=trig,
            substitute_id="sub-1",
            lesson_outline=[{"period": 1, "topic": "Algebra", "materials": ["worksheet"]}],
        )
        self.assertEqual(packet.lesson_outline[0]["topic"], "Algebra")

    def test_candidate_ranking_prefers_department_priority_then_load(self) -> None:
        candidates = [
            SubstituteCandidate("2", "Low load", "+2", "math", 0, 0),
            SubstituteCandidate("3", "Priority", "+3", "math", 4, 10),
            SubstituteCandidate("4", "Other department", "+4", "science", 0, 50),
            SubstituteCandidate("1", "Absent", "+1", "math", 0, 99),
        ]
        ranked = rank_substitute_candidates(
            absent_teacher_id="1",
            candidates=candidates,
            required_department_id="math",
        )
        self.assertEqual([candidate.teacher_id for candidate in ranked], ["3", "2", "4"])

    def test_broadcast_falls_back_to_sms(self) -> None:
        calls = []

        def whatsapp(*args, **kwargs):
            calls.append("whatsapp")
            return False

        def sms(*args, **kwargs):
            calls.append("sms")
            return True

        results = broadcast_substitute_request(
            school=type("School", (), {"pk": 1, "name": "Test School"})(),
            candidates=[SubstituteCandidate("2", "Cover", "+15550001")],
            work_date="2026-06-09",
            send_whatsapp_fn=whatsapp,
            send_sms_fn=sms,
        )
        self.assertEqual(calls, ["whatsapp", "sms"])
        self.assertTrue(results[0].accepted)
        self.assertEqual(results[0].channel, "sms")
