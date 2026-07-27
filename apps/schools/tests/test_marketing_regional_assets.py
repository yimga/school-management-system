"""Regional marketing asset matrix coverage for top-10 markets."""
from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from apps.schools.marketing_media_matrix import (
    LOOP_BUCKETS,
    apm_icons_for_country,
    assets_for_country,
    loop_bucket_for_country,
)

TOP_TEN = ("US", "GB", "CA", "SA", "AE", "NG", "KE", "IN", "BR", "ID")


class MarketingRegionalAssetsTests(SimpleTestCase):
    def test_top_ten_resolve_buckets(self):
        buckets = {loop_bucket_for_country(cc) for cc in TOP_TEN}
        self.assertTrue(buckets.issubset(set(LOOP_BUCKETS)))
        self.assertGreater(len(buckets), 1)

    def test_assets_have_loop_paths(self):
        for cc in TOP_TEN:
            assets = assets_for_country(cc)
            self.assertTrue(assets["sovereign_hero_loop_mp4"].endswith(".mp4"))
            self.assertTrue(assets["sovereign_hero_loop_webm"].endswith(".webm"))

    def test_apm_icons_non_empty(self):
        for cc in TOP_TEN:
            icons = apm_icons_for_country(cc)
            self.assertGreaterEqual(len(icons), 1)
            self.assertIn("label", icons[0])

    @unittest.skipUnless(
        shutil.which("ffmpeg"),
        "ffmpeg required: distinct regional loop mp4s are derived from the hero via "
        "ffmpeg; without it every bucket is the same 275B placeholder (identical hash), "
        "so this on-disk distinctness check fails for an environment reason, not a bug.",
    )
    def test_loop_mp4_buckets_are_distinct_on_disk(self):
        repo = Path(__file__).resolve().parents[3]
        manifest = repo / "docs" / "generated" / "marketing_media_manifest.json"
        static = repo / "static"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        digests: set[str] = set()
        for bucket, paths in (data.get("loops") or {}).items():
            mp4 = static / paths["mp4"]
            self.assertTrue(mp4.is_file(), f"{bucket} missing {mp4}")
            digest = hashlib.sha256(mp4.read_bytes()).hexdigest()
            self.assertNotIn(digest, digests, f"{bucket} duplicates another loop mp4")
            digests.add(digest)
