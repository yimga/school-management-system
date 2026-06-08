from django.test import SimpleTestCase, override_settings

from apps.sync_engine.delta_bundle import (
    export_delta_bundle,
    verify_and_parse_bundle,
)


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY="sync-test-key")
class DeltaBundleTests(SimpleTestCase):
    def test_round_trip_is_tenant_bound(self):
        data = export_delta_bundle(
            school_id=7,
            device_id="device-a",
            rows=[{"entity": "student_note", "id": "1", "value": "draft"}],
        )
        rows, errors = verify_and_parse_bundle(data, expected_school_id=7)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["entity"], "student_note")

        rows, errors = verify_and_parse_bundle(data, expected_school_id=8)
        self.assertEqual(rows, [])
        self.assertEqual(errors, ["school_mismatch"])

    def test_tamper_is_rejected(self):
        data = export_delta_bundle(
            school_id=7,
            rows=[{"entity": "student_note", "id": "1"}],
        )
        tampered = data.replace(b"student_note", b"lesson_plan", 1)
        rows, errors = verify_and_parse_bundle(tampered, expected_school_id=7)
        self.assertEqual(rows, [])
        self.assertEqual(errors, ["signature_mismatch"])
