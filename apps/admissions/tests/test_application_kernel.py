"""Wave R-B (v3.96.0 — 2026-05-26) — Admission application kernel tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.admissions.application_kernel import (
    ACCEPTED,
    APPLIED,
    ENROLLED,
    LEAD,
    REJECTED,
    UNDER_REVIEW,
    EnrollmentResult,
    InvalidStageTransition,
    advance_stage,
    attach_document_reference,
    build_summary,
    can_enroll,
    can_transition,
    enroll_applicant_to_student,
    get_application_payload,
    get_document_spec,
    list_all_documents,
    list_required_documents,
    remove_document_reference,
)


class DocumentRegistryTests(SimpleTestCase):

    def test_required_documents_subset(self):
        required = {d.key for d in list_required_documents()}
        all_keys = {d.key for d in list_all_documents()}
        self.assertTrue(required.issubset(all_keys))
        self.assertIn("birth_certificate", required)
        self.assertIn("immunization_record", required)

    def test_unknown_key_returns_none(self):
        self.assertIsNone(get_document_spec("does-not-exist"))


class StageFSMTests(SimpleTestCase):

    def test_lead_can_apply(self):
        self.assertTrue(can_transition(LEAD, APPLIED))

    def test_lead_cannot_jump_to_accepted(self):
        self.assertFalse(can_transition(LEAD, ACCEPTED))

    def test_accepted_can_revert_to_under_review(self):
        self.assertTrue(can_transition(ACCEPTED, UNDER_REVIEW))

    def test_enrolled_is_terminal(self):
        for s in (LEAD, APPLIED, UNDER_REVIEW, ACCEPTED, REJECTED):
            self.assertFalse(can_transition(ENROLLED, s))

    def test_invalid_transition_raises(self):
        with self.assertRaises(InvalidStageTransition):
            advance_stage(
                current_stage=LEAD, target_stage=ENROLLED, extra_data={},
            )

    def test_advance_records_history(self):
        new_stage, new_extra = advance_stage(
            current_stage=LEAD, target_stage=APPLIED,
            extra_data={}, actor_id=42, note="initial",
        )
        self.assertEqual(new_stage, APPLIED)
        history = new_extra["application"]["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["from"], LEAD)
        self.assertEqual(history[0]["to"], APPLIED)
        self.assertEqual(history[0]["actor_id"], 42)

    def test_same_stage_is_noop_but_valid(self):
        # Useful for replays — should not raise.
        new_stage, new_extra = advance_stage(
            current_stage=APPLIED, target_stage=APPLIED, extra_data={},
        )
        self.assertEqual(new_stage, APPLIED)


class DocumentAttachTests(SimpleTestCase):

    def test_attach_unknown_doc_raises(self):
        with self.assertRaises(ValueError):
            attach_document_reference(
                extra_data={}, document_key="invented", storage_ref="s3://x",
            )

    def test_attach_then_remove(self):
        d = attach_document_reference(
            extra_data={}, document_key="birth_certificate",
            storage_ref="s3://tenant/abc.pdf",
        )
        docs = d["application"]["documents"]
        self.assertTrue(docs["birth_certificate"]["received"])

        d2 = remove_document_reference(
            extra_data=d, document_key="birth_certificate",
        )
        self.assertNotIn("birth_certificate", d2["application"]["documents"])

    def test_attach_requires_storage_ref(self):
        with self.assertRaises(ValueError):
            attach_document_reference(
                extra_data={}, document_key="birth_certificate", storage_ref="",
            )

    def test_extra_data_preserves_unrelated_keys(self):
        seed = {"lead_score": 0.74, "campaign": "spring-2026"}
        out = attach_document_reference(
            extra_data=seed, document_key="birth_certificate",
            storage_ref="s3://x.pdf",
        )
        self.assertEqual(out["lead_score"], 0.74)
        self.assertEqual(out["campaign"], "spring-2026")


class SummaryTests(SimpleTestCase):

    def test_summary_empty(self):
        s = build_summary(stage=LEAD, extra_data={})
        self.assertEqual(s.document_count_received, 0)
        self.assertGreater(s.document_count_required, 0)
        self.assertFalse(s.is_document_complete)

    def test_summary_after_full_attach(self):
        extra = {}
        for spec in list_required_documents():
            extra = attach_document_reference(
                extra_data=extra, document_key=spec.key,
                storage_ref=f"s3://x/{spec.key}.pdf",
            )
        s = build_summary(stage=APPLIED, extra_data=extra)
        self.assertTrue(s.is_document_complete)
        self.assertEqual(s.required_outstanding, [])


class CanEnrollTests(SimpleTestCase):

    def test_wrong_stage_blocks(self):
        ok, blockers = can_enroll(current_stage=APPLIED, extra_data={})
        self.assertFalse(ok)
        self.assertTrue(any(b.startswith("applicant_must_be_accepted") for b in blockers))

    def test_missing_docs_block(self):
        ok, blockers = can_enroll(current_stage=ACCEPTED, extra_data={})
        self.assertFalse(ok)
        self.assertTrue(any(b.startswith("required_documents_outstanding") for b in blockers))

    def test_passes_with_accepted_and_full_docs(self):
        extra = {}
        for spec in list_required_documents():
            extra = attach_document_reference(
                extra_data=extra, document_key=spec.key,
                storage_ref=f"s3://x/{spec.key}.pdf",
            )
        ok, blockers = can_enroll(current_stage=ACCEPTED, extra_data=extra)
        self.assertTrue(ok)
        self.assertEqual(blockers, [])


class EnrollmentRunnerSeamTests(SimpleTestCase):

    def test_runner_is_called_with_args(self):
        captured = {}

        def fake_runner(**kw):
            captured.update(kw)
            return EnrollmentResult(ok=True, student_id=12345)

        result = enroll_applicant_to_student(
            applicant_id=42, school_id=7, actor_user_id=99,
            db_runner=fake_runner,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.student_id, 12345)
        self.assertEqual(captured["applicant_id"], 42)
        self.assertEqual(captured["school_id"], 7)
        self.assertEqual(captured["actor_user_id"], 99)


class PayloadShapeTests(SimpleTestCase):

    def test_empty_payload_returns_canonical_shape(self):
        p = get_application_payload(None)
        self.assertIn("documents", p)
        self.assertIn("history", p)
        self.assertIn("metadata", p)
        self.assertEqual(p["documents"], {})
        self.assertEqual(p["history"], [])

    def test_existing_payload_not_mutated(self):
        seed = {"application": {"documents": {"k": {"received": True}}}}
        p = get_application_payload(seed)
        p["documents"]["k"]["received"] = False  # mutate copy
        # original untouched
        self.assertTrue(seed["application"]["documents"]["k"]["received"])
