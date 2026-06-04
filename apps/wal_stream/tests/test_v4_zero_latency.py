"""v4.00.0 zero-latency mandate — unit coverage for the pure-Python kernels.

SimpleTestCase only — no DB required. The integration paths (Channels consumer,
Redis stream, Celery drainer) need a live Redis + ASGI server and are exercised
in the next-layer integration suite. These tests pin the contracts the new
modules are documented to honor.
"""

from __future__ import annotations

import json
import time

from django.test import SimpleTestCase, override_settings

from apps.tenancy.middleware_rls_jwt import _verify_jwt, mint_rls_jwt
from apps.wal_stream.consumers import _validate
from services.prompt_shaping import (
    MAX_COMPLETION_TOKENS,
    VALID_VIEWPORTS,
    normalize_viewport,
    shape,
)
from services.rls_jwt_signing import (
    HSMBackendNotConfigured,
    LOCAL_BACKEND,
    HSM_BACKENDS,
    active_backend,
    reset_signer_cache,
    sign,
    verify,
)


class PromptShapingTests(SimpleTestCase):
    def test_normalize_viewport_accepts_known_values(self):
        for vp in VALID_VIEWPORTS:
            self.assertEqual(normalize_viewport(vp), vp)
            self.assertEqual(normalize_viewport(vp.lower()), vp)

    def test_normalize_viewport_falls_back_to_a(self):
        self.assertEqual(normalize_viewport(None), "A")
        self.assertEqual(normalize_viewport(""), "A")
        self.assertEqual(normalize_viewport("Z"), "A")

    def test_shape_viewport_c_strips_decorative_blocks(self):
        prompt = (
            "Add a student.\n"
            "<schema>{ massive nested schema doc here }</schema>\n"
            "<docs>multi-paragraph doc</docs>\n"
            "<examples>3 example payloads</examples>\n"
            "Confirm with single action."
        )
        shaped = shape(prompt, viewport="C")
        self.assertNotIn("<schema>", shaped.prompt)
        self.assertNotIn("<docs>", shaped.prompt)
        self.assertNotIn("<examples>", shaped.prompt)
        self.assertIn("Add a student.", shaped.prompt)
        self.assertIn("Confirm with single action.", shaped.prompt)
        self.assertEqual(shaped.max_completion_tokens, MAX_COMPLETION_TOKENS["C"])

    def test_shape_viewport_a_preserves_full_prompt(self):
        prompt = "Add a student.\n<schema>{ doc }</schema>\nThanks."
        shaped = shape(prompt, viewport="A")
        self.assertIn("<schema>", shaped.prompt)
        self.assertEqual(shaped.max_completion_tokens, MAX_COMPLETION_TOKENS["A"])

    def test_shape_extra_system_extends_canonical(self):
        shaped = shape("hi", viewport="B", extra_system=("Cite tenant context.",))
        self.assertIn("Cite tenant context.", shaped.system_messages)


@override_settings(RMC_RLS_JWT_SIGNING_KEY="test-key-32-chars-1234567890ab",
                   RMC_RLS_JWT_SIGNING_BACKEND="local-env-key")
class RLSJWTRoundTripTests(SimpleTestCase):
    def setUp(self):
        reset_signer_cache()

    def test_round_trip_token_is_decoded(self):
        token = mint_rls_jwt(school_id="abc-123", user_id=42, role="teacher")
        claims = _verify_jwt(token)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["school_id"], "abc-123")
        self.assertEqual(claims["user_id"], "42")
        self.assertEqual(claims["role"], "teacher")

    def test_tampered_payload_rejected(self):
        token = mint_rls_jwt(school_id="abc-123", user_id=1, role="parent")
        header, _payload, sig = token.split(".")
        # Forge a new payload (different school) but keep the original signature.
        forged_payload = "ZXZpbA"  # base64url of "evil"
        bad = f"{header}.{forged_payload}.{sig}"
        self.assertIsNone(_verify_jwt(bad))

    def test_expired_token_rejected(self):
        # We can't easily roll the iat; verify a token with a known-old iat is rejected.
        # Build it by hand using the same sign() path.
        import base64

        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"school_id": "abc-123", "user_id": "1", "role": "parent", "iat": int(time.time()) - 99999}
        h64 = base64.urlsafe_b64encode(json.dumps(header, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=").decode()
        p64 = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).rstrip(b"=").decode()
        sig = sign(f"{h64}.{p64}".encode())
        s64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
        self.assertIsNone(_verify_jwt(f"{h64}.{p64}.{s64}"))


class HSMBackendTests(SimpleTestCase):
    def setUp(self):
        reset_signer_cache()

    def test_local_backend_signs_and_verifies(self):
        with override_settings(RMC_RLS_JWT_SIGNING_BACKEND="local-env-key"):
            reset_signer_cache()
            self.assertEqual(active_backend(), LOCAL_BACKEND)
            sig = sign(b"hello")
            self.assertTrue(verify(b"hello", sig))
            self.assertFalse(verify(b"goodbye", sig))

    def test_hsm_backends_refuse_until_configured(self):
        for backend in HSM_BACKENDS:
            with override_settings(RMC_RLS_JWT_SIGNING_BACKEND=backend):
                reset_signer_cache()
                self.assertEqual(active_backend(), backend)
                with self.assertRaises(HSMBackendNotConfigured):
                    sign(b"hello")

    def test_unknown_backend_falls_back_to_local(self):
        with override_settings(RMC_RLS_JWT_SIGNING_BACKEND="not-a-real-backend"):
            reset_signer_cache()
            # active_backend() still returns the local fallback for the signer.
            self.assertEqual(active_backend(), LOCAL_BACKEND)
            sig = sign(b"x")
            self.assertTrue(verify(b"x", sig))


class WALEnvelopeValidationTests(SimpleTestCase):
    TENANT = "deadbeefcafe"

    def _envelope(self, **overrides):
        env = {
            "txn_id": "abcd1234ef56",
            "vector_clock": 1,
            "domain": "attendance",
            "actions": [{"student_id": "s1", "session_id": "x", "status": "present", "marked_at": "now"}],
            "tenant_hash": self.TENANT,
        }
        env.update(overrides)
        return env

    def test_happy_path_validates(self):
        ok, reason = _validate(self._envelope(), expected_tenant_hash=self.TENANT)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "")

    def test_bad_txn_id_rejected(self):
        ok, reason = _validate(self._envelope(txn_id="x"), expected_tenant_hash=self.TENANT)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_txn_id")

    def test_bad_vector_clock_rejected(self):
        ok, reason = _validate(self._envelope(vector_clock=-1), expected_tenant_hash=self.TENANT)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_vector_clock")

    def test_unknown_domain_rejected(self):
        ok, reason = _validate(self._envelope(domain="not_a_domain"), expected_tenant_hash=self.TENANT)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_domain")

    def test_empty_actions_rejected(self):
        ok, reason = _validate(self._envelope(actions=[]), expected_tenant_hash=self.TENANT)
        self.assertFalse(ok)
        self.assertEqual(reason, "no_actions")

    def test_tenant_mismatch_rejected(self):
        ok, reason = _validate(self._envelope(tenant_hash="aaaaaaaaaaaa"), expected_tenant_hash=self.TENANT)
        self.assertFalse(ok)
        self.assertEqual(reason, "tenant_mismatch")

    def test_oversize_envelope_rejected(self):
        massive = self._envelope(actions=[{"k": "x" * 600}] * 500)  # ~300 KiB
        ok, reason = _validate(massive, expected_tenant_hash=self.TENANT)
        self.assertFalse(ok)
        self.assertEqual(reason, "too_large")


class WALWriterDispatchTests(SimpleTestCase):
    def test_dispatch_rejects_unknown_domain(self):
        from apps.wal_stream.writers import dispatch

        with self.assertRaises(ValueError):
            dispatch({"domain": "bogus", "actions": []})

    def test_dispatch_accepts_registered_domains(self):
        from apps.wal_stream.writers import _REGISTRY

        for domain in ("attendance", "teacher_attendance", "grade", "communication_send", "announcement_create", "audit_event"):
            self.assertIn(domain, _REGISTRY)

    def test_billing_charge_domain_is_intentionally_removed(self):
        # The old billing_charge writer built Invoice() with non-existent fields
        # and silently lost money; it had no client producer. It must stay out of
        # the registry + consumer allow-list until rebuilt against the real
        # Invoice contract with DB tests.
        from apps.wal_stream.consumers import _ALLOWED_DOMAINS
        from apps.wal_stream.writers import _REGISTRY

        self.assertNotIn("billing_charge", _REGISTRY)
        self.assertNotIn("billing_charge", _ALLOWED_DOMAINS)

    def test_teacher_attendance_domain_is_validated_by_consumer(self):
        from apps.wal_stream.consumers import _validate

        env = {
            "txn_id": "abcd1234ef56",
            "vector_clock": 1,
            "domain": "teacher_attendance",
            "actions": [{"teacher_id": 7, "date": "2026-05-28", "status": "PRESENT"}],
            "tenant_hash": "deadbeefcafe",
        }
        ok, reason = _validate(env, expected_tenant_hash="deadbeefcafe")
        self.assertTrue(ok, reason)

    def test_safe_decimal_handles_strings_and_numbers(self):
        from decimal import Decimal

        from apps.wal_stream.writers import _safe_decimal

        self.assertEqual(_safe_decimal("87.5"), Decimal("87.5"))
        self.assertEqual(_safe_decimal(80), Decimal("80"))
        self.assertIsNone(_safe_decimal(None))
        self.assertIsNone(_safe_decimal(""))
        self.assertIsNone(_safe_decimal("not-a-number"))

    def test_grade_writer_skips_when_envelope_has_no_user(self):
        from apps.wal_stream.writers import _apply_grade

        # No envelope user_id -> writer logs and returns; no exception.
        env = {"actions": [{"student_id": 1, "subject_assignment_id": 33,
                            "academic_year_id": 11, "term_id": 22, "seq1_score": 80}]}
        _apply_grade(env)  # must not raise

    def test_teacher_attendance_writer_normalizes_status_case(self):
        """Writer must uppercase 'present'/'Absent' and reject unknown enum to 'PRESENT'.

        Mock TeacherAttendance.objects to avoid DB and assert the rows handed to
        bulk_create carry the normalized status.
        """
        from unittest import mock

        env = {"actions": [
            {"teacher_id": 1, "date": "2026-05-28", "status": "present"},
            {"teacher_id": 2, "date": "2026-05-28", "status": "Absent"},
            {"teacher_id": 3, "date": "2026-05-28", "status": "BOGUS"},
        ]}
        captured_rows: list = []

        def _fake_bulk_create(rows, **kwargs):
            captured_rows.extend(rows)

        with mock.patch("apps.people.models.TeacherAttendance.objects.bulk_create", side_effect=_fake_bulk_create):
            from apps.wal_stream.writers import _apply_teacher_attendance

            _apply_teacher_attendance(env)
        statuses = sorted(r.status for r in captured_rows)
        self.assertEqual(statuses, ["ABSENT", "PRESENT", "PRESENT"])  # BOGUS -> PRESENT


class ResolveAttendanceSessionTests(SimpleTestCase):
    """The WAL JS sends session_id="<classroom_id>::<date>" to keep the wire compact.

    The writer's helper must unpack that into (classroom_id, date) AND honor
    explicit fields when both are present.
    """

    def test_explicit_fields_win(self):
        from apps.wal_stream.writers import _resolve_attendance_session

        c, d = _resolve_attendance_session({"classroom_id": 7, "date": "2026-05-28"})
        self.assertEqual((c, d), (7, "2026-05-28"))

    def test_session_marker_unpacked(self):
        from apps.wal_stream.writers import _resolve_attendance_session

        c, d = _resolve_attendance_session({"session_id": "42::2026-05-28"})
        self.assertEqual((c, d), ("42", "2026-05-28"))

    def test_session_marker_overridden_by_explicit_classroom(self):
        from apps.wal_stream.writers import _resolve_attendance_session

        c, d = _resolve_attendance_session({
            "classroom_id": 99,
            "session_id": "42::2026-05-28",
        })
        # Explicit classroom_id wins; date pulled from marker.
        self.assertEqual((c, d), (99, "2026-05-28"))

    def test_missing_both_returns_none(self):
        from apps.wal_stream.writers import _resolve_attendance_session

        c, d = _resolve_attendance_session({"student_id": "x"})
        self.assertIsNone(c)
        self.assertIsNone(d)


class EdgeCacheKeyTests(SimpleTestCase):
    def test_surrogate_key_format(self):
        from services.edge_cache import surrogate_key_for

        key = surrogate_key_for(tenant="acme", view="school_calendar", viewport="A")
        self.assertEqual(key, "acme::/api/v1/runtime/calendar::v=A")

    def test_unknown_view_falls_through_to_pattern(self):
        from services.edge_cache import surrogate_key_for

        key = surrogate_key_for(tenant="acme", view="not_a_view", viewport="B")
        self.assertEqual(key, "acme::/api/v1/runtime/not_a_view::v=B")

    def test_missing_tenant_uses_underscore(self):
        from services.edge_cache import surrogate_key_for

        key = surrogate_key_for(tenant="", view="school_calendar", viewport="C")
        self.assertTrue(key.startswith("_::"))
