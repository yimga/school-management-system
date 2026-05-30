"""Tests for multimodal_terminology runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import multimodal_terminology as mmt


class MultimodalTerminologyTests(unittest.TestCase):
    def test_upsert_requires_all_fields(self) -> None:
        result = mmt.upsert({"term_key": "x"})
        self.assertEqual(result["status"], "rejected")
        self.assertIn("iso_alpha2", result["missing"])

    def test_upsert_and_resolve(self) -> None:
        mmt.upsert({
            "term_key": "principal",
            "iso_alpha2": "DE",
            "label_native": "Schulleiter",
            "transliteration": "Schulleiter",
            "audio_url": "/x",
            "sign_language_video_url": "/y",
        })
        resolved = mmt.resolve("principal", iso_alpha2="DE")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["label_native"], "Schulleiter")
