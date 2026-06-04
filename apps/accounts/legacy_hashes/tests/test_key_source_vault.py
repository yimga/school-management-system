"""Tests for SH-6 Vault-sourced field-encryption key ring.

DB-free ``SimpleTestCase`` + mocked ``urllib``/env, so robust to the Windows
SQLite-lock artifact. Verifies the critical guarantee: when the source is NOT
'vault' (the default), nothing reaches the network and the env path is used.
"""

from __future__ import annotations

import json
import urllib.error
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.accounts.legacy_hashes import key_source_vault as ksv


def _kv_v2_body(field_value):
    return json.dumps({"data": {"data": {"keys": field_value}, "metadata": {}}}).encode("utf-8")


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ParseRingTests(SimpleTestCase):
    def test_list_passthrough(self):
        self.assertEqual(ksv._parse_ring(["a", "b", " c "]), ["a", "b", "c"])

    def test_json_array_string(self):
        self.assertEqual(ksv._parse_ring('["x", "y"]'), ["x", "y"])

    def test_comma_separated(self):
        self.assertEqual(ksv._parse_ring("x, y ,z"), ["x", "y", "z"])

    def test_newline_separated(self):
        self.assertEqual(ksv._parse_ring("x\ny\n"), ["x", "y"])

    def test_empty(self):
        self.assertEqual(ksv._parse_ring(""), [])
        self.assertEqual(ksv._parse_ring(None), [])


class SourceGateTests(SimpleTestCase):
    def setUp(self):
        ksv.reset_cache_for_tests()

    def test_default_source_returns_none_no_network(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch("urllib.request.urlopen") as urlopen:
            self.assertIsNone(ksv.load_keys_from_vault())
            urlopen.assert_not_called()

    def test_explicit_env_source_returns_none(self):
        with mock.patch.dict("os.environ", {"DJANGO_CRYPTOGRAPHY_KEYS_SOURCE": "env"}, clear=True):
            self.assertIsNone(ksv.load_keys_from_vault())

    def test_dry_run_returns_none_no_network(self):
        env = {
            "DJANGO_CRYPTOGRAPHY_KEYS_SOURCE": "vault",
            "DJANGO_CRYPTOGRAPHY_VAULT_DRY_RUN": "1",
            "VAULT_ADDR": "https://vault.example",
            "VAULT_TOKEN": "t",
            "DJANGO_CRYPTOGRAPHY_VAULT_PATH": "rmc/crypto",
        }
        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch("urllib.request.urlopen") as urlopen:
            self.assertIsNone(ksv.load_keys_from_vault())
            urlopen.assert_not_called()


class FailLoudTests(SimpleTestCase):
    def setUp(self):
        ksv.reset_cache_for_tests()

    def _env(self, **overrides):
        env = {"DJANGO_CRYPTOGRAPHY_KEYS_SOURCE": "vault"}
        env.update(overrides)
        return env

    def test_missing_token_raises(self):
        env = self._env(VAULT_ADDR="https://v", DJANGO_CRYPTOGRAPHY_VAULT_PATH="p")
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaises(ksv.VaultKeySourceError):
                ksv.load_keys_from_vault()

    def test_missing_path_raises(self):
        env = self._env(VAULT_ADDR="https://v", VAULT_TOKEN="t")
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaises(ksv.VaultKeySourceError):
                ksv.load_keys_from_vault()

    def test_bad_addr_raises(self):
        env = self._env(VAULT_ADDR="not-a-url", VAULT_TOKEN="t", DJANGO_CRYPTOGRAPHY_VAULT_PATH="p")
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaises(ksv.VaultKeySourceError):
                ksv.load_keys_from_vault()

    def test_empty_keys_field_raises(self):
        env = self._env(VAULT_ADDR="https://v", VAULT_TOKEN="t", DJANGO_CRYPTOGRAPHY_VAULT_PATH="p")
        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch("urllib.request.urlopen", return_value=_FakeResp(_kv_v2_body(""))):
            with self.assertRaises(ksv.VaultKeySourceError):
                ksv.load_keys_from_vault()

    def test_non_kv2_shape_raises(self):
        env = self._env(VAULT_ADDR="https://v", VAULT_TOKEN="t", DJANGO_CRYPTOGRAPHY_VAULT_PATH="p")
        body = json.dumps({"data": {"keys": ["x"]}}).encode("utf-8")  # missing inner data
        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch("urllib.request.urlopen", return_value=_FakeResp(body)):
            with self.assertRaises(ksv.VaultKeySourceError):
                ksv.load_keys_from_vault()


class SuccessAndCacheTests(SimpleTestCase):
    def setUp(self):
        ksv.reset_cache_for_tests()

    def _env(self):
        return {
            "DJANGO_CRYPTOGRAPHY_KEYS_SOURCE": "vault",
            "VAULT_ADDR": "https://vault.example",
            "VAULT_TOKEN": "t",
            "DJANGO_CRYPTOGRAPHY_VAULT_PATH": "rmc/crypto",
        }

    def test_success_json_array(self):
        with mock.patch.dict("os.environ", self._env(), clear=True), \
                mock.patch("urllib.request.urlopen", return_value=_FakeResp(_kv_v2_body(["k1", "k2"]))):
            keys = ksv.load_keys_from_vault()
        self.assertEqual(keys, ["k1", "k2"])

    def test_success_comma_string(self):
        with mock.patch.dict("os.environ", self._env(), clear=True), \
                mock.patch("urllib.request.urlopen", return_value=_FakeResp(_kv_v2_body("k1, k2"))):
            keys = ksv.load_keys_from_vault()
        self.assertEqual(keys, ["k1", "k2"])

    def test_cache_avoids_second_network_call(self):
        with mock.patch.dict("os.environ", self._env(), clear=True), \
                mock.patch("urllib.request.urlopen", return_value=_FakeResp(_kv_v2_body(["k1"]))) as urlopen:
            first = ksv.load_keys_from_vault()
            second = ksv.load_keys_from_vault()
        self.assertEqual(first, ["k1"])
        self.assertEqual(second, ["k1"])
        self.assertEqual(urlopen.call_count, 1)


class StaleServeTests(SimpleTestCase):
    """Transient Vault failure serves the last-known-good ring (never switches
    source); a failure with no cached ring fails loud."""

    def setUp(self):
        ksv.reset_cache_for_tests()

    def _env(self):
        # cache TTL 0 forces a refresh on every call so we can exercise the
        # transient-failure path after a successful prime.
        return {
            "DJANGO_CRYPTOGRAPHY_KEYS_SOURCE": "vault",
            "VAULT_ADDR": "https://vault.example",
            "VAULT_TOKEN": "t",
            "DJANGO_CRYPTOGRAPHY_VAULT_PATH": "rmc/crypto",
            "DJANGO_CRYPTOGRAPHY_VAULT_CACHE_SECONDS": "0",
        }

    def test_serves_stale_after_transient_error(self):
        with mock.patch.dict("os.environ", self._env(), clear=True):
            with mock.patch("urllib.request.urlopen", return_value=_FakeResp(_kv_v2_body(["k1"]))):
                primed = ksv.load_keys_from_vault()
            self.assertEqual(primed, ["k1"])
            with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("vault down")):
                served = ksv.load_keys_from_vault()
        self.assertEqual(served, ["k1"])  # last-known-good, not a raise

    def test_raises_on_transient_error_without_cache(self):
        env = self._env()
        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(ksv.VaultKeySourceError):
                ksv.load_keys_from_vault()


class EncryptionResolverIntegrationTests(SimpleTestCase):
    """The resolver in encryption.py honors the Vault source when opted in,
    and is unchanged (Vault no-op) by default."""

    def setUp(self):
        ksv.reset_cache_for_tests()

    def test_resolver_uses_vault_keys_when_present(self):
        from apps.accounts.legacy_hashes import encryption

        key = "A" * 44  # 44-char placeholder; resolver only encodes to ascii
        with mock.patch(
            "apps.accounts.legacy_hashes.key_source_vault.load_keys_from_vault",
            return_value=[key],
        ):
            out = encryption._resolve_fernet_key_list()
        self.assertEqual(out, [key.encode("ascii")])

    @override_settings(DJANGO_CRYPTOGRAPHY_KEYS=[])
    def test_resolver_falls_through_when_vault_noop(self):
        from apps.accounts.legacy_hashes import encryption

        envkey = "B" * 44
        with mock.patch(
            "apps.accounts.legacy_hashes.key_source_vault.load_keys_from_vault",
            return_value=None,
        ), mock.patch.dict("os.environ", {"DJANGO_CRYPTOGRAPHY_KEY": envkey}, clear=True):
            out = encryption._resolve_fernet_key_list()
        self.assertEqual(out, [envkey.encode("ascii")])
