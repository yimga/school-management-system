"""Runtime tests for apps.global_registries.schema_mapping (batch 1493)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.global_registries.schema_mapping import (
    CanonicalField,
    SchemaMappingError,
    canonical_fields,
    lookup,
    map_custom_field,
    register_field,
    validate_custom_mapping,
)


class SchemaMappingRuntimeTests(SimpleTestCase):
    def test_core_registry_has_critical_field_keys(self) -> None:
        keys = {f.key for f in canonical_fields()}
        for must in (
            "identity.given_name",
            "identity.family_name",
            "identity.date_of_birth",
            "contact.primary_email",
            "enrollment.grade",
            "academic.transcript_year",
            "attendance.percent_term",
            "guardian.primary_contact",
            "dual_profile.formal_id",
        ):
            self.assertIn(must, keys, f"missing {must}")

    def test_map_custom_field_heuristic_hits(self) -> None:
        self.assertEqual(map_custom_field("First Name").key, "identity.given_name")
        self.assertEqual(map_custom_field("DOB").key, "identity.date_of_birth")
        self.assertEqual(map_custom_field("phone-number").key, "contact.primary_phone")
        self.assertEqual(map_custom_field("guardian phone").key, "guardian.primary_contact")

    def test_validate_custom_mapping_flags_unmapped(self) -> None:
        result = validate_custom_mapping(
            custom_field_keys=["First Name", "favourite_dinosaur"],
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.unmapped_keys, ["favourite_dinosaur"])
        self.assertIn("First Name", result.mapped)

    def test_register_field_rejects_unknown_type(self) -> None:
        with self.assertRaises(SchemaMappingError):
            register_field(CanonicalField("x.bad", "not_a_type", "x"))

    def test_lookup_returns_none_for_unknown(self) -> None:
        self.assertIsNone(lookup("noexist.key"))
