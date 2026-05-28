"""v4.00.13 — unit tests for apps/platform_runtime/jit_operator_controller.py."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.jit_operator_controller import (
    _OPERATOR_FORBIDDEN_FIELDS,
    apply_regional_mask,
    check_jit_authorization,
    compose_operator_view,
    gdpr_resolver,
)


class CheckJITAuthorizationTests(SimpleTestCase):
    def test_no_operator_id_denies(self):
        result = check_jit_authorization(operator_user_id=None, school_settings={})
        self.assertFalse(result.granted)
        self.assertEqual(result.reason, "no-operator-id")

    def test_zero_operator_id_denies(self):
        result = check_jit_authorization(operator_user_id=0, school_settings={})
        self.assertFalse(result.granted)

    def test_no_settings_denies(self):
        result = check_jit_authorization(operator_user_id=5, school_settings=None)
        self.assertFalse(result.granted)
        self.assertEqual(result.reason, "no-school-settings")

    def test_malformed_access_denies(self):
        result = check_jit_authorization(
            operator_user_id=5,
            school_settings={"operator_access": "not-a-dict"},
        )
        self.assertFalse(result.granted)
        self.assertEqual(result.reason, "malformed-access")

    def test_no_grants_denies(self):
        result = check_jit_authorization(
            operator_user_id=5,
            school_settings={"operator_access": {"jit_grants": []}},
        )
        self.assertFalse(result.granted)
        self.assertEqual(result.reason, "no-grants")

    def test_expired_grant_denies(self):
        result = check_jit_authorization(
            operator_user_id=5,
            school_settings={
                "operator_access": {
                    "jit_grants": [
                        {"operator_user_id": 5, "expires_at_iso": "2020-01-01T00:00:00+00:00"},
                    ],
                },
            },
            now_iso="2026-05-28T00:00:00+00:00",
        )
        self.assertFalse(result.granted)
        self.assertEqual(result.reason, "no-live-grant")

    def test_live_grant_allows(self):
        result = check_jit_authorization(
            operator_user_id=5,
            school_settings={
                "operator_access": {
                    "jit_grants": [
                        {"operator_user_id": 5, "expires_at_iso": "2030-01-01T00:00:00+00:00", "reason": "audit"},
                    ],
                },
            },
            now_iso="2026-05-28T00:00:00+00:00",
        )
        self.assertTrue(result.granted)
        self.assertEqual(result.reason, "audit")

    def test_different_operator_id_denies(self):
        result = check_jit_authorization(
            operator_user_id=99,
            school_settings={
                "operator_access": {
                    "jit_grants": [
                        {"operator_user_id": 5, "expires_at_iso": "2030-01-01T00:00:00+00:00"},
                    ],
                },
            },
            now_iso="2026-05-28T00:00:00+00:00",
        )
        self.assertFalse(result.granted)


class GDPRResolverTests(SimpleTestCase):
    def test_forbidden_fields_denied(self):
        for f in ["ssn", "passport_number", "password", "totp_secret"]:
            self.assertFalse(gdpr_resolver(f, region="US"), f"{f} should be forbidden")

    def test_non_forbidden_allowed(self):
        self.assertTrue(gdpr_resolver("classroom_name", region="EU"))
        self.assertTrue(gdpr_resolver("attendance_status", region=None))

    def test_empty_field_allowed(self):
        self.assertTrue(gdpr_resolver("", region="EU"))


class ApplyRegionalMaskTests(SimpleTestCase):
    def test_no_region_no_mask(self):
        record = {"first_name": "Alice", "id": 1}
        self.assertEqual(apply_regional_mask(record, region=None), record)

    def test_eu_masks_name_and_email(self):
        record = {"first_name": "Alice", "email": "a@b.com", "grade": "A"}
        out = apply_regional_mask(record, region="EU")
        self.assertNotEqual(out["first_name"], "Alice")
        self.assertNotIn("Alice", out["first_name"])
        self.assertNotEqual(out["email"], "a@b.com")
        self.assertEqual(out["grade"], "A", "non-masked fields pass through")

    def test_de_normalizes_to_eu(self):
        out = apply_regional_mask({"first_name": "Bob"}, region="DE")
        self.assertNotIn("Bob", out["first_name"])

    def test_us_normalizes_to_ccpa(self):
        # CCPA masks first_name + last_name + full_name (not email/phone)
        out = apply_regional_mask({"first_name": "Bob", "email": "x@y.com"}, region="US")
        self.assertNotIn("Bob", out["first_name"])
        self.assertEqual(out["email"], "x@y.com", "CCPA does not mask email")

    def test_mask_preserves_structure(self):
        out = apply_regional_mask({"email": "alice@example.com"}, region="EU")
        masked = out["email"]
        self.assertEqual(masked.count("@"), 1, "@ structure preserved")
        self.assertEqual(masked.count("."), 1, ". structure preserved")
        self.assertNotIn("alice", masked)
        self.assertNotIn("example", masked)


class ComposeOperatorViewTests(SimpleTestCase):
    def test_no_grant_returns_empty(self):
        grant, visible = compose_operator_view(
            operator_user_id=None,
            school_settings={},
            region="EU",
            record={"first_name": "Alice"},
        )
        self.assertFalse(grant.granted)
        self.assertEqual(visible, {})

    def test_granted_with_mask(self):
        settings = {
            "operator_access": {
                "jit_grants": [
                    {"operator_user_id": 5, "expires_at_iso": "2030-01-01T00:00:00+00:00", "reason": "audit"},
                ],
            },
        }
        grant, visible = compose_operator_view(
            operator_user_id=5,
            school_settings=settings,
            region="EU",
            record={"first_name": "Alice", "ssn": "123-45-6789", "class_size": 30},
            now_iso="2026-05-28T00:00:00+00:00",
        )
        self.assertTrue(grant.granted)
        self.assertNotIn("ssn", visible, "forbidden field dropped")
        self.assertNotIn("Alice", visible["first_name"], "name masked")
        self.assertEqual(visible["class_size"], 30, "non-masked passes through")


class ForbiddenFieldsContractTests(SimpleTestCase):
    """Pin the forbidden set so renaming it is a deliberate act."""

    def test_critical_fields_in_forbidden_set(self):
        for required in {"ssn", "passport_number", "password", "password_hash", "totp_secret"}:
            self.assertIn(required, _OPERATOR_FORBIDDEN_FIELDS)
