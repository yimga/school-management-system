"""Tests for ``apps.compliance.tenant_export_integrity``."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.compliance.tenant_export_integrity import (
    build_manifest,
    compute_export_hash,
    manifest_to_json,
    verify_manifest,
)


class ComputeExportHashTests(SimpleTestCase):
    def test_hash_is_64_char_hex_sha256(self):
        digest = compute_export_hash(b"x,y,z\n1,2,3\n")
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))

    def test_hash_is_deterministic(self):
        a = compute_export_hash(b"a,b\n")
        b = compute_export_hash(b"a,b\n")
        self.assertEqual(a, b)

    def test_distinct_bytes_distinct_hash(self):
        self.assertNotEqual(
            compute_export_hash(b"a"),
            compute_export_hash(b"A"),
        )

    def test_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            compute_export_hash("string-not-bytes")  # type: ignore[arg-type]


class BuildManifestTests(SimpleTestCase):
    def setUp(self):
        self.school = SimpleNamespace(id=42, slug="oak-prep", name="Oak Preparatory")
        self.payload = b"student_id,grade\n101,A\n102,B\n"
        self.when = datetime(2026, 5, 17, 14, 0, tzinfo=timezone.utc)

    def test_manifest_carries_tenant_identity(self):
        m = build_manifest(
            school=self.school, export_key="waec_wassce_student_summary",
            payload=self.payload, generated_at=self.when,
        )
        self.assertEqual(m["school_id"], 42)
        self.assertEqual(m["school_slug"], "oak-prep")
        self.assertEqual(m["school_name"], "Oak Preparatory")
        self.assertEqual(m["export_key"], "waec_wassce_student_summary")
        self.assertEqual(m["generated_at"], "2026-05-17T14:00:00+00:00")
        self.assertEqual(m["byte_count"], len(self.payload))
        self.assertEqual(m["hash_algorithm"], "sha256")
        self.assertEqual(m["schema_version"], 1)

    def test_manifest_hash_matches_payload(self):
        m = build_manifest(
            school=self.school, export_key="x", payload=self.payload, generated_at=self.when,
        )
        self.assertEqual(m["hash_hex"], compute_export_hash(self.payload))

    def test_missing_school_id_rejected(self):
        bad = SimpleNamespace(slug="x", name="X")
        with self.assertRaises(ValueError):
            build_manifest(school=bad, export_key="x", payload=b"", generated_at=self.when)

    def test_extra_metadata_carried_through(self):
        m = build_manifest(
            school=self.school, export_key="x", payload=b"x",
            generated_at=self.when, extra={"region": "GH", "format": "csv"},
        )
        self.assertEqual(m["extra"], {"region": "GH", "format": "csv"})


class VerifyManifestTests(SimpleTestCase):
    def setUp(self):
        self.school = SimpleNamespace(id=1, slug="t", name="T")
        self.payload = b"hello,world\n"
        self.manifest = build_manifest(
            school=self.school, export_key="x", payload=self.payload,
        )

    def test_verify_returns_true_for_unmodified_bytes(self):
        self.assertTrue(verify_manifest(self.manifest, self.payload))

    def test_verify_returns_false_for_modified_bytes(self):
        self.assertFalse(verify_manifest(self.manifest, self.payload + b" "))

    def test_verify_returns_false_for_empty_manifest(self):
        self.assertFalse(verify_manifest({}, self.payload))

    def test_verify_returns_false_for_non_dict_manifest(self):
        self.assertFalse(verify_manifest(None, self.payload))  # type: ignore[arg-type]
        self.assertFalse(verify_manifest("not-a-dict", self.payload))  # type: ignore[arg-type]

    def test_manifest_to_json_is_stable_sorted(self):
        text = manifest_to_json(self.manifest)
        keys_in_order = [
            "byte_count", "export_key", "generated_at",
            "hash_algorithm", "hash_hex", "schema_version",
            "school_id", "school_name", "school_slug",
        ]
        last_idx = -1
        for k in keys_in_order:
            idx = text.find(f'"{k}"')
            self.assertGreater(idx, last_idx, f"key {k} out of order in serialized manifest")
            last_idx = idx
