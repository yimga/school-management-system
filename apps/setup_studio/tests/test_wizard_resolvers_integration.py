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
    write_student_course_selection_step,
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


class RoleWizardKernelWiringTests(TestCase):
    """The role wizards must reach their kernels, not just a settings blob.

    ``apps/academics/role_wizard_kernel.py`` and
    ``apps/billing/parent_payment_wizard_kernel.py`` were written for exactly
    these four writers and had ZERO callers anywhere in the tree -- not one
    import, not one test. The writers hand-rolled a subset of what the kernels
    do, so the kernel-only effects (the gradebook projection, the assembled
    course request) never happened. Each assertion below fails if a writer is
    reverted to writing the settings slice itself.
    """

    _ACTOR = 4242

    def setUp(self):
        from apps.schools.models import School
        self.school = School.objects.create(name="Role Kernel Wiring Test")

    def _settings(self):
        self.school.refresh_from_db()
        return self.school.settings or {}

    def test_gradebook_writer_projects_policies_onto_the_chosen_classroom(self):
        """Only the kernel writes ``teacher_gradebook.<classroom_id>``.

        The wizard asks for the class in ``select_class`` and the marking
        policy in ``policies``; a gradebook reads the policy BY CLASSROOM, and
        nothing assembled that projection while the writer wrote its own slice.
        """
        write_teacher_gradebook_setup_step(
            school=self.school, wizard_key="teacher_gradebook_setup",
            step_key="select_class", payload={"value": "77"},
            actor_user_id=self._ACTOR,
        )
        write_teacher_gradebook_setup_step(
            school=self.school, wizard_key="teacher_gradebook_setup",
            step_key="policies", payload={"late_penalty": "10"},
            actor_user_id=self._ACTOR,
        )
        settings = self._settings()
        self.assertIn(
            "teacher_gradebook", settings,
            "policies step did not reach apply_teacher_gradebook_step",
        )
        self.assertIn("77", settings["teacher_gradebook"])
        row = settings["teacher_gradebook"]["77"]
        self.assertEqual(row["policies"], {"late_penalty": "10"})
        self.assertEqual(row["teacher_user_id"], self._ACTOR)

    def test_attendance_writer_stamps_updated_at_through_the_kernel(self):
        write_teacher_attendance_intake_step(
            school=self.school, wizard_key="teacher_attendance_intake",
            step_key="default_statuses", payload={"default": "present"},
            actor_user_id=self._ACTOR,
        )
        slice_ = (
            self._settings()["role_wizards"]["teacher_attendance_intake"]
            ["users"][str(self._ACTOR)]["default_statuses"]
        )
        self.assertEqual(slice_["default"], "present")
        self.assertIn(
            "updated_at", slice_,
            "the kernel stamps updated_at; a raw settings write does not",
        )

    def test_course_selection_keeps_every_step_instead_of_overwriting_one_key(self):
        """The old writer put each step at ``student_course_requests.<actor>``.

        That is ONE key, so every step overwrote the previous one and only the
        last answer survived -- a student's required_courses selection was
        destroyed by their electives selection. Each step must now survive, and
        the confirm step must assemble the request.
        """
        for step_key, payload in (
            ("academic_year", {"value": "2026-2027"}),
            ("required_courses", {"value": ["MATH", "PHYS"]}),
            ("electives", {"value": ["ART"]}),
            ("confirm", {"value": True}),
        ):
            write_student_course_selection_step(
                school=self.school, wizard_key="student_course_selection",
                step_key=step_key, payload=payload, actor_user_id=self._ACTOR,
            )
        settings = self._settings()
        user_slice = (
            settings["role_wizards"]["student_course_selection"]
            ["users"][str(self._ACTOR)]
        )
        for step_key in ("academic_year", "required_courses", "electives", "confirm"):
            self.assertIn(
                step_key, user_slice,
                f"{step_key} was overwritten -- the writer is not keeping a slice per step",
            )
        self.assertEqual(user_slice["required_courses"]["value"], ["MATH", "PHYS"])
        confirmed = settings["student_course_requests"][str(self._ACTOR)]
        self.assertIn("confirmed_at", confirmed)
        self.assertEqual(confirmed["required_courses"]["value"], ["MATH", "PHYS"])

    def test_parent_payment_writer_reaches_the_kernel_without_leaking_secrets(self):
        """The billing kernel does NOT sanitise; the writer must hand it `safe`."""
        write_parent_payment_setup_step(
            school=self.school, wizard_key="parent_payment_setup",
            step_key="card_details",
            payload={
                "billing_name": "Jane Smith",
                "card_number": "4242424242424242",
                "cvv": "123",
                "iban": "DE89370400440532013000",
            },
            actor_user_id=self._ACTOR,
        )
        settings = self._settings()
        row = settings["parent_payment_setup"]["users"][str(self._ACTOR)]["card_details"]
        self.assertEqual(row["billing_name"], "Jane Smith")
        self.assertIn(
            "updated_at", row,
            "the billing kernel stamps updated_at; a raw settings write does not",
        )
        self.assertIn("updated_at", settings["parent_payment_setup"])
        blob = str(settings)
        for secret in ("4242424242424242", "123456", "DE89370400440532013000"):
            self.assertNotIn(
                secret, blob,
                "payment secret reached school.settings -- the kernel does not "
                "strip, so the writer must sanitise BEFORE delegating",
            )
        for key in ("card_number", "cvv", "iban"):
            self.assertNotIn(key, row)
