"""Batch 14 mapping: siteconfig DynamicField* ↔ metadata DynamicField*."""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.metadata.dynamic_field_reconciliation import (
    metadata_definition_data_type_to_siteconfig,
    metadata_value_json_to_siteconfig_columns,
    siteconfig_definition_data_type_to_metadata,
    siteconfig_value_to_metadata_value_json,
)


class DynamicFieldReconciliationMappingTests(SimpleTestCase):
    def test_definition_data_type_round_trip(self):
        for sc in ("TEXT", "NUMBER", "DATE", "BOOLEAN", "JSON"):
            meta = siteconfig_definition_data_type_to_metadata(sc)
            self.assertEqual(metadata_definition_data_type_to_siteconfig(meta), sc)

    def test_unknown_siteconfig_type_defaults_to_string(self):
        self.assertEqual(siteconfig_definition_data_type_to_metadata("WEIRD"), "string")

    def test_unknown_metadata_type_defaults_to_text(self):
        self.assertEqual(metadata_definition_data_type_to_siteconfig("unknown"), "TEXT")

    def test_text_value(self):
        self.assertEqual(
            siteconfig_value_to_metadata_value_json(
                siteconfig_data_type="TEXT", value_text="hello"
            ),
            {"v": "hello"},
        )

    def test_number_decimal(self):
        self.assertEqual(
            siteconfig_value_to_metadata_value_json(
                siteconfig_data_type="NUMBER", value_number=Decimal("3.5")
            )["v"],
            3.5,
        )

    def test_date_iso(self):
        d = date(2026, 3, 27)
        self.assertEqual(
            siteconfig_value_to_metadata_value_json(
                siteconfig_data_type="DATE", value_date=d
            ),
            {"v": "2026-03-27"},
        )

    def test_boolean_from_text(self):
        self.assertEqual(
            siteconfig_value_to_metadata_value_json(
                siteconfig_data_type="BOOLEAN", value_text="true"
            ),
            {"v": True},
        )
        self.assertEqual(
            siteconfig_value_to_metadata_value_json(
                siteconfig_data_type="BOOLEAN", value_text=""
            ),
            {"v": False},
        )

    def test_json_payload(self):
        blob = {"a": 1}
        self.assertEqual(
            siteconfig_value_to_metadata_value_json(
                siteconfig_data_type="JSON", value_json=blob
            ),
            {"v": blob},
        )

    def test_metadata_string_to_siteconfig_columns(self):
        cols = metadata_value_json_to_siteconfig_columns(
            metadata_data_type="string", value_json={"v": "x"}
        )
        self.assertEqual(cols["value_text"], "x")

    def test_metadata_number_to_siteconfig_columns(self):
        cols = metadata_value_json_to_siteconfig_columns(
            metadata_data_type="number", value_json={"v": 42}
        )
        self.assertEqual(cols["value_number"], 42)

    def test_metadata_date_to_siteconfig_columns(self):
        cols = metadata_value_json_to_siteconfig_columns(
            metadata_data_type="date", value_json={"v": "2026-01-15"}
        )
        self.assertEqual(cols["value_date"], date(2026, 1, 15))

    def test_metadata_boolean_to_siteconfig_columns(self):
        cols = metadata_value_json_to_siteconfig_columns(
            metadata_data_type="boolean", value_json={"v": True}
        )
        self.assertEqual(cols["value_text"], "true")

    def test_metadata_json_to_siteconfig_columns(self):
        cols = metadata_value_json_to_siteconfig_columns(
            metadata_data_type="json", value_json={"v": [1, 2]}
        )
        self.assertEqual(cols["value_json"], [1, 2])
