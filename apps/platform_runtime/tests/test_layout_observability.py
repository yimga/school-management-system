from django.test import SimpleTestCase

from apps.platform_runtime.layout_observability import sanitize_layout_observation


class LayoutObservationSanitizerTests(SimpleTestCase):
    def test_rejects_unknown_schema_version(self):
        self.assertEqual(sanitize_layout_observation({"version": 2}), {})

    def test_keeps_only_bounded_content_free_fields(self):
        result = sanitize_layout_observation(
            {
                "version": 1,
                "observed_count": 8,
                "overflow_count": 4,
                "inline_overflow_count": 3,
                "block_overflow_count": 2,
                "max_inline_overflow_px": 900,
                "max_block_overflow_px": 12,
                "viewport_class": "c",
                "direction": "rtl",
                "visual_viewport_width": 390.4,
                "visual_viewport_height": 844.2,
                "text": "private student name",
                "selector": "#tenant-secret",
            }
        )
        self.assertEqual(result["viewport_class"], "C")
        self.assertEqual(result["direction"], "rtl")
        self.assertEqual(result["visual_viewport_width"], 390)
        self.assertNotIn("text", result)
        self.assertNotIn("selector", result)

    def test_counts_cannot_exceed_parent_counts(self):
        result = sanitize_layout_observation(
            {
                "version": 1,
                "observed_count": 2,
                "overflow_count": 50,
                "inline_overflow_count": 40,
                "block_overflow_count": 30,
            }
        )
        self.assertEqual(result["overflow_count"], 2)
        self.assertEqual(result["inline_overflow_count"], 2)
        self.assertEqual(result["block_overflow_count"], 2)

    def test_rejects_negative_and_boolean_values(self):
        result = sanitize_layout_observation(
            {
                "version": 1,
                "observed_count": -1,
                "overflow_count": True,
                "max_inline_overflow_px": "not-a-number",
            }
        )
        self.assertNotIn("observed_count", result)
        self.assertEqual(result["overflow_count"], 0)
        self.assertNotIn("max_inline_overflow_px", result)
