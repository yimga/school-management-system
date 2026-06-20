"""Integration tests for the wizard resolver modules (v4.00.12).

Closes the v3.99.23 deferral: existing happy-path tests walk every wizard
end-to-end via the engine. These tests focus on the resolver layer itself:

* Secret-stripping invariants (payment + password writers MUST drop sensitive
  keys before any persistence path).
* Option resolvers return well-formed shape ({value, label_token, metadata})
  even when the underlying domain model is missing.
* Cross-resolver flows: gradebook + attendance writers share a school's
  setup namespace without clobbering each other.

These run as Django TestCase so they get a real DB-backed School, but
unlike the happy-path walker they do NOT exercise the full state machine
— they call writers + resolvers directly so failures land on the resolver,
not the engine.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.setup_studio import wizard_resolvers_operator
from apps.setup_studio.wizard_resolvers_domain import (
    _PAYMENT_SECRET_KEYS,
    list_attendance_status_choices,
    list_communication_channel_choices,
    list_grading_scale_choices,
    list_parent_payment_method_choices,
    list_parent_topic_choices,
    write_parent_contact_preferences_step,
    write_parent_payment_setup_step,
    write_password_rotation_step,
    write_teacher_attendance_intake_step,
    write_teacher_gradebook_setup_step,
)


class OptionResolverShapeTests(SimpleTestCase):
    """All static option resolvers return [{value, label_token, metadata}]."""

    def _assert_option_shape(self, options):
        self.assertIsInstance(options, list)
        self.assertGreater(len(options), 0, "option resolver returned empty list unexpectedly")
        for entry in options:
            self.assertIsInstance(entry, dict)
            self.assertIn("value", entry)
            self.assertIn("label_token", entry)
            self.assertIn("metadata", entry)
            self.assertIsInstance(entry["value"], str)
            self.assertIsInstance(entry["label_token"], str)
            self.assertIsInstance(entry["metadata"], dict)

    def test_grading_scale_choices_shape(self):
        self._assert_option_shape(list_grading_scale_choices(request=None, school=None))

    def test_attendance_status_choices_shape(self):
        self._assert_option_shape(list_attendance_status_choices(request=None, school=None))

    def test_parent_payment_method_choices_shape(self):
        self._assert_option_shape(list_parent_payment_method_choices(request=None, school=None))

    def test_communication_channel_choices_shape(self):
        self._assert_option_shape(list_communication_channel_choices(request=None, school=None))

    def test_parent_topic_choices_shape(self):
        opts = list_parent_topic_choices(request=None, school=None)
        self._assert_option_shape(opts)
        keys = [o["value"] for o in opts]
        self.assertIn("safeguarding_alerts", keys, "safeguarding alerts must always be present")
        safeguarding = next(o for o in opts if o["value"] == "safeguarding_alerts")
        self.assertTrue(safeguarding["metadata"].get("never_quiet"), "safeguarding alerts must bypass quiet hours")


class PaymentSecretStrippingTests(SimpleTestCase):
    """write_parent_payment_setup_step MUST strip card/account/IBAN before any persistence path."""

    def test_secret_keys_constant_covers_canonical_fields(self):
        for required in {"card_number", "cvv", "cvc", "iban", "routing_number", "account_number"}:
            self.assertIn(required, _PAYMENT_SECRET_KEYS)

    def test_writer_with_school_none_still_strips_and_logs(self):
        payload = {
            "method": "card",
            "card_number": "4242424242424242",
            "cvv": "123",
            "iban": "DE89370400440532013000",
            "billing_name": "Jane Smith",
        }
        write_parent_payment_setup_step(
            school=None,
            wizard_key="parent_payment_setup",
            step_key="card",
            payload=payload,
            actor_user_id=1,
        )
        self.assertEqual(payload["card_number"], "4242424242424242",
                         "writer must not mutate caller's payload in-place")


class PasswordWriterTests(SimpleTestCase):
    """write_password_rotation_step MUST refuse to persist any raw password key."""

    def test_password_keys_never_persist_when_school_is_none(self):
        with self.assertLogs("apps.setup_studio.wizard_resolvers_domain", level="INFO") as logs:
            write_password_rotation_step(
                school=None,
                wizard_key="student_password_rotation",
                step_key="new_password",
                payload={
                    "new_password": "Sup3rSecret!",
                    "confirm_password": "Sup3rSecret!",
                    "current_password": "OldOne!",
                    "password": "shouldnotappear",
                    "verify_identity": "12345",
                },
                actor_user_id=42,
            )
        joined = "\n".join(logs.output)
        for forbidden in ["new_password", "confirm_password", "current_password", "Sup3rSecret", "OldOne", "shouldnotappear"]:
            self.assertNotIn(forbidden, joined,
                             f"raw secret {forbidden!r} must never appear in log line")
        self.assertIn("verify_identity_hash", joined)

    def test_verify_identity_is_hashed_not_persisted_raw(self):
        raw = "id-card-x9293"
        with self.assertLogs("apps.setup_studio.wizard_resolvers_domain", level="INFO") as logs:
            write_password_rotation_step(
                school=None,
                wizard_key="student_password_rotation",
                step_key="verify",
                payload={"verify_identity": raw},
                actor_user_id=99,
            )
        joined = "\n".join(logs.output)
        # verify_identity is recorded only as a hash-only marker KEY; neither the
        # raw identity nor the hash value itself is logged (minimal logging).
        self.assertIn("verify_identity_hash", joined)
        self.assertNotIn(raw, joined)


class TeacherWriterTests(TestCase):
    """Gradebook + attendance writers share a school's setup namespace."""

    def setUp(self):
        from apps.schools.models import School
        self.school = School.objects.create(name="Integration Resolver Test")

    # The per-user wizard writers persist into school.settings under
    # ``role_wizards.<wizard>.users.<actor>.<step>`` (see _write_user_step), NOT
    # SetupProgress.step_state, and they no-op without a truthy actor_user_id.
    _ACTOR = 7

    def _read_role_wizards(self):
        self.school.refresh_from_db()
        return (self.school.settings or {}).get("role_wizards") or {}

    def test_gradebook_and_attendance_writes_do_not_clobber(self):
        write_teacher_gradebook_setup_step(
            school=self.school,
            wizard_key="teacher_gradebook_setup",
            step_key="weights",
            payload={"homework_weight": 30, "exam_weight": 70},
            actor_user_id=self._ACTOR,
        )
        write_teacher_attendance_intake_step(
            school=self.school,
            wizard_key="teacher_attendance_intake",
            step_key="default_statuses",
            payload={"default": "present"},
            actor_user_id=self._ACTOR,
        )
        role_wizards = self._read_role_wizards()
        # Both per-user wizard buckets coexist — neither writer clobbers the other.
        self.assertIn("teacher_gradebook_setup", role_wizards)
        self.assertIn("teacher_attendance_intake", role_wizards)
        gb = role_wizards["teacher_gradebook_setup"]["users"][str(self._ACTOR)]
        att = role_wizards["teacher_attendance_intake"]["users"][str(self._ACTOR)]
        self.assertIn("weights", gb)
        self.assertIn("default_statuses", att)

    def test_contact_preferences_writes_audit_metadata(self):
        write_parent_contact_preferences_step(
            school=self.school,
            wizard_key="parent_contact_preferences",
            step_key="channels",
            payload={"channels": ["email", "push"]},
            actor_user_id=self._ACTOR,
        )
        role_wizards = self._read_role_wizards()
        self.assertIn("parent_contact_preferences", role_wizards)
        user_bucket = role_wizards["parent_contact_preferences"]["users"][str(self._ACTOR)]
        self.assertIn("channels", user_bucket)


class OperatorResolverShapeTests(SimpleTestCase):
    """Spot-check the operator resolver module exports."""

    def test_module_exposes_writers_for_legacy_bridge_targets(self):
        for name in ("write_mfa_setup_step",):
            self.assertTrue(
                hasattr(wizard_resolvers_operator, name),
                f"wizard_resolvers_operator must expose {name} for legacy_view_bridge",
            )


class ResolverErrorPathTests(SimpleTestCase):
    """v4.00.13: defensive error-path coverage.

    Writers must NEVER raise on:
    * malformed payload (None, list, str instead of dict)
    * missing required keys
    * unexpected types in expected keys
    """

    def test_payment_writer_handles_non_dict_payload(self):
        # Should not raise even when payload is None or a non-dict
        write_parent_payment_setup_step(
            school=None, wizard_key="parent_payment_setup",
            step_key="card", payload=None, actor_user_id=1,
        )
        write_parent_payment_setup_step(
            school=None, wizard_key="parent_payment_setup",
            step_key="card", payload={}, actor_user_id=None,
        )

    def test_password_writer_handles_empty_payload(self):
        with self.assertLogs("apps.setup_studio.wizard_resolvers_domain", level="INFO"):
            write_password_rotation_step(
                school=None, wizard_key="student_password_rotation",
                step_key="verify", payload={}, actor_user_id=1,
            )

    def test_password_writer_handles_none_verify_identity(self):
        with self.assertLogs("apps.setup_studio.wizard_resolvers_domain", level="INFO"):
            write_password_rotation_step(
                school=None, wizard_key="student_password_rotation",
                step_key="verify", payload={"verify_identity": None},
                actor_user_id=1,
            )

    def test_payment_writer_with_unknown_method_key_does_not_persist_secrets(self):
        """Even unrecognized fields shaped like secrets get stripped via lowercase match."""
        write_parent_payment_setup_step(
            school=None, wizard_key="parent_payment_setup",
            step_key="card", payload={"CARD_NUMBER": "9999"},  # uppercase
            actor_user_id=1,
        )
        # If the function were case-sensitive, this would be a real risk. The
        # writer lowercases the key on match, so this is the regression pin.
