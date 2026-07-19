"""The DR-snapshot durability knobs must actually take effect when set.

Regression guard for the exact bug this wave fixed: ``TENANT_SNAPSHOT_S3_BUCKET``
and the snapshot dir overrides were READ (via ``getattr(settings, ...)``) but
NEVER DECLARED in settings, so an operator who set the env var got nothing —
``getattr`` fell through to ``None`` and the S3 leg was permanently dead. Now that
settings read them from the environment, setting the value must flow through to
``_snapshot_roots`` and ``_maybe_upload_object_storage``.

These are ``SimpleTestCase`` (filesystem + settings only, no DB, no task registry).
"""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from apps.lifecycle.tenant_dr_snapshot import (
    _assert_or_warn_snapshot_durability,
    _maybe_upload_object_storage,
    _snapshot_roots,
    snapshot_durability_status,
)


class SnapshotRootOverrideTests(SimpleTestCase):
    def test_secondary_dir_override_redirects_the_second_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            sep = str(Path(tmp) / "independent_secondary")
            with override_settings(TENANT_SNAPSHOT_SECONDARY_DIR=sep):
                primary, secondary = _snapshot_roots()
            self.assertEqual(str(secondary), str(Path(sep)))
            self.assertTrue(secondary.is_dir())
            # Primary keeps its default (the two stores are now on different roots).
            self.assertNotEqual(str(primary), str(secondary))

    def test_primary_dir_override_redirects_the_first_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            pep = str(Path(tmp) / "independent_primary")
            with override_settings(TENANT_SNAPSHOT_PRIMARY_DIR=pep):
                primary, _secondary = _snapshot_roots()
            self.assertEqual(str(primary), str(Path(pep)))
            self.assertTrue(primary.is_dir())

    def test_no_override_keeps_legacy_var_paths(self):
        # Blank overrides => unchanged historical behaviour (backward compatible).
        with override_settings(
            TENANT_SNAPSHOT_PRIMARY_DIR="", TENANT_SNAPSHOT_SECONDARY_DIR=""
        ):
            primary, secondary = _snapshot_roots()
        self.assertTrue(primary.as_posix().endswith("var/tenant_snapshots/primary"))
        self.assertTrue(secondary.as_posix().endswith("var/tenant_snapshots/secondary"))

    def test_default_layout_is_ephemeral_dual_dir(self):
        """Metric #28 — same-device primary/secondary is not independent durability."""
        with override_settings(
            TENANT_SNAPSHOT_PRIMARY_DIR="",
            TENANT_SNAPSHOT_SECONDARY_DIR="",
            TENANT_SNAPSHOT_S3_BUCKET="",
        ):
            status = snapshot_durability_status()
        self.assertEqual(status["class"], "ephemeral_dual_dir")
        self.assertFalse(status["independent"])
        self.assertTrue(status["same_device"])

    def test_s3_bucket_marks_object_storage_independent(self):
        with override_settings(
            TENANT_SNAPSHOT_PRIMARY_DIR="",
            TENANT_SNAPSHOT_SECONDARY_DIR="",
            TENANT_SNAPSHOT_S3_BUCKET="dr-bucket",
        ):
            status = snapshot_durability_status()
        self.assertEqual(status["class"], "object_storage")
        self.assertTrue(status["independent"])

    def test_require_independent_raises_on_ephemeral(self):
        with override_settings(
            TENANT_SNAPSHOT_PRIMARY_DIR="",
            TENANT_SNAPSHOT_SECONDARY_DIR="",
            TENANT_SNAPSHOT_S3_BUCKET="",
            TENANT_SNAPSHOT_REQUIRE_INDEPENDENT_STORES=True,
        ):
            primary, secondary = _snapshot_roots()
            with self.assertRaises(RuntimeError) as ctx:
                _assert_or_warn_snapshot_durability(primary, secondary)
        self.assertIn("ephemeral_dual_dir", str(ctx.exception))

    def test_require_independent_allows_when_s3_configured(self):
        with override_settings(
            TENANT_SNAPSHOT_PRIMARY_DIR="",
            TENANT_SNAPSHOT_SECONDARY_DIR="",
            TENANT_SNAPSHOT_S3_BUCKET="dr-bucket",
            TENANT_SNAPSHOT_REQUIRE_INDEPENDENT_STORES=True,
        ):
            primary, secondary = _snapshot_roots()
            status = _assert_or_warn_snapshot_durability(primary, secondary)
        self.assertEqual(status["class"], "object_storage")


class S3WiringTests(SimpleTestCase):
    def test_unset_bucket_skips_s3(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "blob.json.gz"
            local.write_bytes(b"x")
            with override_settings(TENANT_SNAPSHOT_S3_BUCKET=""):
                self.assertIsNone(
                    _maybe_upload_object_storage(local_path=local, object_key="k")
                )

    def test_set_bucket_flows_through_to_upload(self):
        """With the bucket set, the code reaches boto3 and uploads.

        Proves the setting is genuinely wired end-to-end. A fake ``boto3`` module
        is injected so the test is deterministic whether or not real boto3 is
        installed, and records the exact (bucket, key) the upload targeted.
        """
        calls: list[tuple] = []

        class _FakeClient:
            def upload_file(self, filename, bucket, key):
                calls.append((filename, bucket, key))

        fake_boto3 = types.ModuleType("boto3")
        fake_boto3.client = lambda *a, **kw: _FakeClient()  # type: ignore[attr-defined]

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "blob.json.gz"
            local.write_bytes(b"payload")
            original = sys.modules.get("boto3")
            sys.modules["boto3"] = fake_boto3
            try:
                with override_settings(
                    TENANT_SNAPSHOT_S3_BUCKET="dr-bucket",
                    TENANT_SNAPSHOT_S3_ENDPOINT="",
                ):
                    uri = _maybe_upload_object_storage(
                        local_path=local, object_key="tenant_snapshots/s/2026-07-17.json.gz"
                    )
            finally:
                if original is None:
                    sys.modules.pop("boto3", None)
                else:
                    sys.modules["boto3"] = original

        self.assertEqual(uri, "s3://dr-bucket/tenant_snapshots/s/2026-07-17.json.gz")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "dr-bucket")
        self.assertEqual(calls[0][2], "tenant_snapshots/s/2026-07-17.json.gz")
