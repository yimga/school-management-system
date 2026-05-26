"""Depth tests for apps.global_registries.schema_mapping (batch 1509)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.global_registries.schema_mapping import (
    CANONICAL_FIELD_TYPES,
    CanonicalField,
    SchemaMappingError,
    canonical_fields,
    lookup,
    map_custom_field,
    register_field,
    validate_custom_mapping,
)


class SchemaMappingDepthTests(SimpleTestCase):
    def test_canonical_registry_contains_expected_minimum(self) -> None:
        fields = canonical_fields()
        keys = {f.key for f in fields}
        for required in (
            "identity.given_name",
            "identity.family_name",
            "identity.date_of_birth",
            "contact.primary_email",
            "enrollment.grade",
            "guardian.primary_contact",
        ):
            self.assertIn(required, keys, f"canonical registry missing {required}")

    def test_lookup_returns_none_for_unknown(self) -> None:
        self.assertIsNone(lookup("definitely.not.a.real.key"))

    def test_map_custom_field_handles_case_and_punctuation(self) -> None:
        self.assertEqual(
            map_custom_field("First Name").key,
            "identity.given_name",
        )
        self.assertEqual(
            map_custom_field("LAST-NAME").key,
            "identity.family_name",
        )
        self.assertEqual(
            map_custom_field("date_of_birth").key,
            "identity.date_of_birth",
        )

    def test_map_custom_field_returns_none_on_blank_or_unknown(self) -> None:
        self.assertIsNone(map_custom_field(""))
        self.assertIsNone(map_custom_field("   "))
        self.assertIsNone(map_custom_field("completely_unmappable_xyz"))

    def test_validate_custom_mapping_reports_unmapped(self) -> None:
        result = validate_custom_mapping(
            custom_field_keys=["First Name", "completely_unmappable_xyz"],
        )
        self.assertFalse(result.ok)
        self.assertIn("completely_unmappable_xyz", result.unmapped_keys)
        self.assertEqual(result.mapped["First Name"], "identity.given_name")

    def test_validate_custom_mapping_all_mapped_returns_ok(self) -> None:
        result = validate_custom_mapping(
            custom_field_keys=["first_name", "last_name", "email"],
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.unmapped_keys, [])
        self.assertEqual(result.mapped["email"], "contact.primary_email")

    def test_validate_transferable_only_filters_non_transferable(self) -> None:
        # Register a fresh non-transferable field that maps from a hint we add.
        from apps.global_registries import schema_mapping as sm

        sm._HEURISTIC_HINTS["scratch_alias_for_test"] = "identity.scratch_internal_test"
        register_field(
            CanonicalField(
                key="identity.scratch_internal_test",
                canonical_type="identity",
                label="scratch",
                transferable=False,
            )
        )
        try:
            result = validate_custom_mapping(
                custom_field_keys=["scratch_alias_for_test"],
                transferable_only=True,
            )
            self.assertFalse(result.ok)
            self.assertIn("scratch_alias_for_test", result.unmapped_keys)
            relaxed = validate_custom_mapping(
                custom_field_keys=["scratch_alias_for_test"],
                transferable_only=False,
            )
            self.assertTrue(relaxed.ok)
        finally:
            sm._HEURISTIC_HINTS.pop("scratch_alias_for_test", None)
            sm._REGISTRY.pop("identity.scratch_internal_test", None)

    def test_register_field_rejects_unknown_canonical_type(self) -> None:
        with self.assertRaises(SchemaMappingError):
            register_field(
                CanonicalField(
                    key="bogus.field",
                    canonical_type="not-a-real-type",
                    label="bogus",
                )
            )

    def test_canonical_field_types_is_immutable_frozenset(self) -> None:
        self.assertIsInstance(CANONICAL_FIELD_TYPES, frozenset)
        with self.assertRaises((AttributeError, TypeError)):
            CANONICAL_FIELD_TYPES.add("hack")  # type: ignore[attr-defined]

    def test_log_emission_omits_unmapped_key_values(self) -> None:
        with self.assertLogs("apps.global_registries.schema_mapping", level="INFO") as cm:
            validate_custom_mapping(
                custom_field_keys=["sensitive_field_name_XYZ"],
            )
        log_text = "\n".join(cm.output)
        # Counts may appear; the raw unmapped key SHOULD NOT.
        self.assertNotIn("sensitive_field_name_XYZ", log_text)
