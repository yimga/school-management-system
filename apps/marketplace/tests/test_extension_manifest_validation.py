"""Linux pillar: extension manifest sandbox validation."""

from django.test import SimpleTestCase

from apps.marketplace.extension_registry import validate_extension_manifest


class ExtensionManifestValidationTests(SimpleTestCase):
    def test_valid_workflow_hook_manifest(self):
        ok, errors = validate_extension_manifest(
            {
                "extension_point": "workflow_hooks",
                "hook_name": "post_enrollment",
                "event_types": ["student.enrolled"],
            }
        )
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_unknown_extension_point_rejected(self):
        ok, errors = validate_extension_manifest(
            {"extension_point": "unknown", "hook_name": "x"}
        )
        self.assertFalse(ok)
        self.assertTrue(any("unknown extension_point" in e for e in errors))

    def test_missing_required_fields(self):
        ok, errors = validate_extension_manifest(
            {"extension_point": "dashboard_cards"}
        )
        self.assertFalse(ok)
        self.assertTrue(len(errors) >= 2)
