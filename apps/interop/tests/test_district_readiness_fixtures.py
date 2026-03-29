"""Stable JSON fixtures for Ed-Fi / CEDS district readiness (SOT §11.4 batch 3 #26)."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.interop.district_readiness import parse_district_readiness_dict


class InteropDistrictReadinessFixtureTests(SimpleTestCase):
    def _load(self, *parts: str) -> dict:
        p = Path(settings.BASE_DIR).joinpath(*parts)
        self.assertTrue(p.is_file(), msg=f"missing fixture {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_edfi_district_sample_shape(self):
        data = self._load("fixtures", "interop", "edfi_district_readiness_sample.json")
        self.assertEqual(data.get("envelope"), "district-readiness-v1")
        self.assertEqual(data.get("sourceSystem"), "edfi")
        self.assertIn("districtIdentifier", data)
        self.assertIn("nameOfInstitution", data)
        self.assertTrue(str(data["districtIdentifier"]).startswith("rmc-"))

    def test_ceds_lea_sample_shape(self):
        data = self._load("fixtures", "interop", "ceds_district_readiness_sample.json")
        self.assertEqual(data.get("envelope"), "district-readiness-v1")
        self.assertEqual(data.get("sourceSystem"), "ceds")
        self.assertIn("leaIdentifier", data)
        self.assertIn("leaName", data)
        self.assertTrue(str(data["leaIdentifier"]).startswith("rmc-"))

    def test_parse_edfi_fixture_round_trip(self):
        data = self._load("fixtures", "interop", "edfi_district_readiness_sample.json")
        out = parse_district_readiness_dict(data)
        self.assertEqual(out["source_system"], "edfi")
        self.assertEqual(out["district_identifier"], data["districtIdentifier"])
        self.assertEqual(out["name"], data["nameOfInstitution"])
        self.assertEqual(out["state_organization_id"], data.get("stateOrganizationId"))

    def test_parse_ceds_fixture_round_trip(self):
        data = self._load("fixtures", "interop", "ceds_district_readiness_sample.json")
        out = parse_district_readiness_dict(data)
        self.assertEqual(out["source_system"], "ceds")
        self.assertEqual(out["district_identifier"], data["leaIdentifier"])
        self.assertEqual(out["name"], data["leaName"])
        self.assertEqual(out["state_abbreviation"], data.get("stateAbbreviation"))

    def test_parse_rejects_unknown_envelope(self):
        with self.assertRaises(ValueError):
            parse_district_readiness_dict({"envelope": "other", "sourceSystem": "edfi"})

    def test_parse_rejects_unknown_source(self):
        with self.assertRaises(ValueError):
            parse_district_readiness_dict(
                {"envelope": "district-readiness-v1", "sourceSystem": "unknown"}
            )
