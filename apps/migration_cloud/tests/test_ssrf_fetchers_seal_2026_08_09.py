"""SSRF / LFI seals for every Migration Cloud server-side fetcher (2026-08-09).

The 2026-08-08 wave sealed ``url_intake._fetch_http`` only. The 2026-08-09
re-audit found the same class OPEN in the two sibling fetchers and latent in a
third, all now routed through the shared ``intake/net_guard.py`` SOT:

  * ``asset_pipeline._fetch_uri`` — ``source_uri`` comes straight off a migrated
    SIS row, so ``file:///etc/passwd`` read the server's disk and
    ``http://169.254.169.254/…`` reached cloud metadata (LIVE via Celery + view).
  * ``api_pull_intake`` — shipped its ``Authorization: Bearer`` token to any host.
  * ``network_resilience._fetch_http_with_range`` / ``_fetch_sftp`` — unmirrored
    (latent) SSRF siblings.

Each test FAILS against the pre-fix code (which connected / read the file) and
PASSES against the guarded fix. No real network is touched: a literal
loopback / link-local IP is rejected by ``getaddrinfo`` shape alone.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings

from apps.migration_cloud import asset_pipeline
from apps.migration_cloud import network_resilience
from apps.migration_cloud.intake import net_guard
from apps.migration_cloud.intake.api_pull_intake import APIPullIntakeAdapter
from apps.migration_cloud.intake.base import IntakeError

_METADATA = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
_LOOPBACK = "http://127.0.0.1/secret"


def _tmp_dest(prefix: str) -> Path:
    """A temp-file path with its fd closed (so Windows can unlink it later)."""
    fd, name = tempfile.mkstemp(prefix=prefix)
    os.close(fd)
    return Path(name)


class AssetPipelineSSRFTests(TestCase):
    """asset_pipeline._fetch_uri — untrusted source_uri is SSRF/LFI guarded."""

    def test_file_scheme_refused_by_default(self):
        # LFI: a migrated row of file:///etc/passwd must NOT read the disk.
        with self.assertRaises(ValueError) as cm:
            asset_pipeline._fetch_uri("file:///etc/passwd")
        self.assertIn("local-file asset source", str(cm.exception))

    def test_bare_local_path_refused_by_default(self):
        with self.assertRaises(ValueError):
            asset_pipeline._fetch_uri("/etc/passwd")

    def test_http_metadata_ip_refused(self):
        with self.assertRaises(IntakeError) as cm:
            asset_pipeline._fetch_uri(_METADATA)
        self.assertIn("non-public", str(cm.exception))

    def test_http_loopback_refused(self):
        with self.assertRaises(IntakeError):
            asset_pipeline._fetch_uri(_LOOPBACK)

    def test_data_uri_over_cap_refused(self):
        big = "A" * 200
        with mock.patch.object(asset_pipeline, "_asset_max_bytes", return_value=10):
            with self.assertRaises(ValueError):
                asset_pipeline._fetch_uri("data:text/plain," + big)

    def test_local_optin_reads_inside_media_root_but_not_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inside = root / "photo.txt"
            inside.write_bytes(b"hello-photo")
            outside = root.parent / "escape_target.txt"
            with override_settings(MEDIA_ROOT=str(root)), \
                    mock.patch.object(
                        asset_pipeline, "_allow_local_file_source", return_value=True,
                    ):
                # Inside MEDIA_ROOT: allowed.
                content, _mime = asset_pipeline._fetch_uri(inside.as_uri())
                self.assertEqual(content, b"hello-photo")
                # Traversal outside MEDIA_ROOT: refused even when opted in.
                with self.assertRaises(ValueError) as cm:
                    asset_pipeline._fetch_uri(outside.as_uri())
                self.assertIn("escapes the allowed asset root", str(cm.exception))


class ApiPullSSRFTests(TestCase):
    """api_pull_intake — host validated public BEFORE the Bearer token is sent."""

    def _pull(self, url):
        adapter = APIPullIntakeAdapter()
        handle = {"url": url, "api_token": "super-secret-token", "artifact_name": "x.json"}
        # Consume the generator so iter_artifacts actually runs.
        return list(adapter.iter_artifacts(handle, None))

    def test_metadata_ip_refused(self):
        with self.assertRaises(IntakeError) as cm:
            self._pull(_METADATA)
        self.assertIn("non-public", str(cm.exception))

    def test_loopback_refused(self):
        with self.assertRaises(IntakeError):
            self._pull(_LOOPBACK)


class NetGuardTests(TestCase):
    """net_guard SOT — public-host assertion + streaming byte cap."""

    def test_assert_public_host_blocks_metadata(self):
        with self.assertRaises(IntakeError):
            net_guard.assert_public_host(_METADATA)

    def test_assert_public_host_allows_public(self):
        # A public host resolves cleanly (uses real DNS; example.com is stable).
        net_guard.assert_public_host("https://example.com/roster.csv")

    def test_fetch_http_capped_enforces_byte_cap(self):
        class _FakeResp:
            headers = {"Content-Type": "text/csv"}

            def __init__(self):
                self._sent = False

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n=-1):
                if self._sent:
                    return b""
                self._sent = True
                return b"A" * 500  # exceeds the 100-byte cap in one chunk

        class _FakeOpener:
            def open(self, req, timeout=None):
                return _FakeResp()

        with mock.patch.object(net_guard, "assert_public_host"), \
                mock.patch.object(
                    net_guard.urllib.request, "build_opener",
                    return_value=_FakeOpener(),
                ):
            with self.assertRaises(IntakeError) as cm:
                net_guard.fetch_http_capped(
                    "https://exports.example.edu/big", max_bytes=100,
                )
            self.assertIn("byte cap", str(cm.exception))


class UrlIntakeFetchHttpMustFireTests(TestCase):
    """Seal the test-integrity gap: the real _fetch_http must invoke the guard."""

    def test_fetch_http_blocks_private_before_network(self):
        from apps.migration_cloud.intake import url_intake

        dest = _tmp_dest("mc_ssrf_")
        try:
            with self.assertRaises(IntakeError) as cm:
                url_intake._fetch_http(_LOOPBACK, dest, max_bytes=100)
            # A missing guard would attempt a real localhost connection and
            # raise a _TransientFetchError ("HTTP fetch failed"), NOT this
            # SSRF message — so the assertion on the message is must-fire.
            self.assertIn("non-public", str(cm.exception))
        finally:
            dest.unlink(missing_ok=True)


class NetworkResilienceSSRFTests(TestCase):
    """network_resilience http/sftp fetchers reject private targets (permanent)."""

    def test_http_range_blocks_private(self):
        dest = _tmp_dest("mc_nr_")
        try:
            with self.assertRaises(network_resilience.FetchError):
                network_resilience._fetch_http_with_range(
                    _LOOPBACK, dest, timeout=1.0, resume_from=0,
                )
        finally:
            dest.unlink(missing_ok=True)

    def test_sftp_blocks_private(self):
        dest = _tmp_dest("mc_nr_")
        try:
            with self.assertRaises(network_resilience.FetchError):
                network_resilience._fetch_sftp(
                    "sftp://127.0.0.1/export.csv", dest, timeout=1.0,
                )
        finally:
            dest.unlink(missing_ok=True)
