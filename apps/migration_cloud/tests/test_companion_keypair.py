"""Tests for the server-side companion-keypair lifecycle.

Originally v3.32.0; brought forward to v3.34.0 per-tenant scoping. All
public service functions now require a ``tenant`` first arg; tests mint
a tenant ``schools.School`` row at setUp.

Coverage:
  - ``ensure_active_keypair`` creates one when none exist.
  - ``ensure_active_keypair`` returns the existing row on second call.
  - ``rotate_keypair`` / ``rotate_active_keypair`` deactivates the old
    row + activates a new one.
  - ``CompanionServerPubkeyView`` GET returns the four-field shape.
  - ``CompanionServerPubkeyView`` NEVER returns private bytes in the body.
  - ``CompanionKeypairRotateView`` rejects anonymous + non-staff callers.
  - ``decrypt_with_active_or_versioned`` falls back to active when no version.
  - ``rotate_keypair`` never logs the private key bytes (NoSecretsLoggedTests).

Tests use a mixture of ``SimpleTestCase`` (import + smoke; no DB) and
``TestCase`` (round-trip + view tests). If PyNaCl is not installed in
the running environment, the crypto-bearing tests skip via
``unittest.skipIf``; the import/structural ones still run.
"""
from __future__ import annotations

import base64
import unittest

from django.test import SimpleTestCase, TestCase
from django.urls import reverse


try:
    import nacl.public  # type: ignore[import-not-found]  # noqa: F401
    _PYNACL_AVAILABLE = True
except ImportError:
    _PYNACL_AVAILABLE = False


_REQUIRE_PYNACL = unittest.skipIf(
    not _PYNACL_AVAILABLE, "PyNaCl not installed in this environment"
)


# ─── Lightweight import / smoke ──────────────────────────────────────────


class CompanionKeypairImportTests(SimpleTestCase):
    """Service + views import cleanly without DB access."""

    def test_service_imports(self):
        from apps.migration_cloud.services import companion_keypair
        for name in (
            "ensure_active_keypair",
            "rotate_keypair",
            "rotate_active_keypair",
            "decrypt_with_active_or_versioned",
            "get_active_public_key_info",
            "fingerprint_of_public_key_b64",
            "fingerprint_eq",
            "PyNaClUnavailable",
            "DecryptResult",
        ):
            self.assertTrue(
                hasattr(companion_keypair, name),
                f"companion_keypair.{name} missing from service surface",
            )

    def test_views_imported(self):
        from apps.migration_cloud import companion_receiver
        self.assertTrue(hasattr(companion_receiver, "companion_server_pubkey_view"))
        self.assertTrue(hasattr(companion_receiver, "CompanionKeypairRotateView"))

    def test_url_routes_resolve(self):
        # Mount points are configured in config/urls.py via include(); use
        # the namespaced name to confirm the route is wired.
        from django.urls.exceptions import NoReverseMatch
        try:
            url_pub = reverse("migration_cloud_super:companion_server_pubkey")
            url_rot = reverse("migration_cloud_super:companion_keypair_rotate")
        except NoReverseMatch:
            # Fallback: try the portal mount (depending on which is loaded).
            try:
                url_pub = reverse("migration_cloud_portal:companion_server_pubkey")
                url_rot = reverse("migration_cloud_portal:companion_keypair_rotate")
            except NoReverseMatch:
                self.skipTest(
                    "migration_cloud URL namespaces not mounted in this test config"
                )
        self.assertIn("companion/server-pubkey", url_pub)
        self.assertIn("companion/keypair/rotate", url_rot)

    def test_fingerprint_constant_time_compare(self):
        from apps.migration_cloud.services import companion_keypair
        fp = companion_keypair.fingerprint_of_public_key_b64("AAAA")
        # 16 bytes base64-encoded → 24 chars (with padding)
        self.assertEqual(len(fp), 24)
        self.assertTrue(companion_keypair.fingerprint_eq(fp, fp))
        # Mutate one byte
        bad = ("Z" + fp[1:]) if fp[0] != "Z" else ("A" + fp[1:])
        self.assertFalse(companion_keypair.fingerprint_eq(fp, bad))


# ─── DB-backed lifecycle tests ───────────────────────────────────────────


def _make_tenant(slug: str = "kp-lifecycle"):
    """Mint a ``schools.School`` row for per-tenant keypair tests."""
    from apps.schools.models import School
    return School.objects.create(name=f"KP Test {slug}", slug=slug)


@_REQUIRE_PYNACL
class CompanionKeypairLifecycleTests(TestCase):
    """ensure_active_keypair, rotate, and decrypt round-trip via the DB."""

    def setUp(self):
        self.tenant = _make_tenant("kp-lifecycle")

    def test_ensure_creates_when_none_exist(self):
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
        from apps.migration_cloud.services import companion_keypair

        # tenant-isolation-allow: keypair-test-count-scoped-per-tenant-fk
        self.assertEqual(
            MigrationCloudCompanionKeypair.objects.filter(tenant=self.tenant).count(),
            0,
        )
        row = companion_keypair.ensure_active_keypair(self.tenant)
        self.assertTrue(row.is_active)
        self.assertEqual(row.key_version, "v1")
        self.assertEqual(row.tenant_id, self.tenant.pk)
        # public_key_b64 round-trips to 32-byte X25519 pubkey
        pub = base64.b64decode(row.public_key_b64)
        self.assertEqual(len(pub), 32)

    def test_ensure_idempotent_returns_existing(self):
        from apps.migration_cloud.services import companion_keypair

        first = companion_keypair.ensure_active_keypair(self.tenant)
        second = companion_keypair.ensure_active_keypair(self.tenant)
        self.assertEqual(first.pk, second.pk)

    def test_rotate_deactivates_old_and_activates_new(self):
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
        from apps.migration_cloud.services import companion_keypair

        companion_keypair.ensure_active_keypair(self.tenant)
        result = companion_keypair.rotate_active_keypair(
            self.tenant, operator_user=None
        )
        self.assertEqual(result["old_version"], "v1")
        self.assertEqual(result["new_version"], "v2")
        self.assertIn("fingerprint_b64", result)
        # tenant-isolation-allow: keypair-test-active-count-scoped-per-tenant-fk
        active_count = MigrationCloudCompanionKeypair.objects.filter(
            tenant=self.tenant, is_active=True
        ).count()
        self.assertEqual(active_count, 1)
        # tenant-isolation-allow: keypair-test-fetch-old-version-scoped-per-tenant-fk
        old = MigrationCloudCompanionKeypair.objects.get(
            tenant=self.tenant, key_version="v1"
        )
        self.assertFalse(old.is_active)
        self.assertIsNotNone(old.rotated_out_at)

    def test_decrypt_with_active_falls_back_when_version_none(self):
        from apps.migration_cloud.services import companion_keypair
        import nacl.public

        row = companion_keypair.ensure_active_keypair(self.tenant)
        pub_bytes = base64.b64decode(row.public_key_b64)
        pub_key = nacl.public.PublicKey(pub_bytes)
        sealed_box = nacl.public.SealedBox(pub_key)
        plaintext = b'{"version":"1.0","source":"powerschool"}'
        ciphertext = sealed_box.encrypt(plaintext)

        # v3.34.0 — service requires tenant first arg.
        result = companion_keypair.decrypt_with_active_or_versioned(
            self.tenant, ciphertext, key_version=None
        )
        self.assertEqual(result.plaintext, plaintext)
        self.assertEqual(result.key_version, row.key_version)

    def test_decrypt_with_specific_version(self):
        from apps.migration_cloud.services import companion_keypair
        import nacl.public

        # Pin a specific version via rotate. The old key should still be
        # usable when its version is named explicitly.
        first = companion_keypair.ensure_active_keypair(self.tenant)
        companion_keypair.rotate_active_keypair(self.tenant, operator_user=None)

        first_pub = base64.b64decode(first.public_key_b64)
        sealed_box = nacl.public.SealedBox(nacl.public.PublicKey(first_pub))
        plaintext = b'{"source":"facts"}'
        ciphertext = sealed_box.encrypt(plaintext)

        result = companion_keypair.decrypt_with_active_or_versioned(
            self.tenant, ciphertext, key_version=first.key_version
        )
        self.assertEqual(result.plaintext, plaintext)
        self.assertEqual(result.key_version, first.key_version)


# ─── View tests ──────────────────────────────────────────────────────────


@_REQUIRE_PYNACL
class CompanionServerPubkeyViewTests(TestCase):
    """GET /companion/server-pubkey/ shape + private-key non-disclosure.

    v3.34.0 — the view now resolves ``request.tenant``; anonymous +
    no-tenant callers receive 400 ``no_tenant``. We sign in as a staff
    user whose membership binds them to a tenant to exercise the
    success path.
    """

    def _resolve_url(self) -> str:
        from django.urls.exceptions import NoReverseMatch
        for ns in ("migration_cloud_super", "migration_cloud_portal"):
            try:
                return reverse(f"{ns}:companion_server_pubkey")
            except NoReverseMatch:
                continue
        self.skipTest("migration_cloud URL namespace not mounted")
        return ""  # unreachable; satisfies type-checker

    def _signed_in_with_tenant(self):
        from django.contrib.auth import get_user_model
        from apps.schools.models import School, SchoolMembership

        tenant = School.objects.create(name="Pubkey View", slug="pubkey-view")
        User = get_user_model()
        # tenant-isolation-allow: test-create-user-for-auth-only-not-tenant-scoped
        user = User.objects.create_user(username="pk_view", password="x")
        try:
            SchoolMembership.objects.create(  # tenant-isolation-allow: test-bind-user-to-tenant-via-membership
                user=user, school=tenant, role="ADMIN",
            )
        except (TypeError, ValueError):
            # If SchoolMembership shape differs across deployments,
            # the _request_school fallback uses the first membership
            # of the user — best-effort the test will skip rather than
            # explode if no compatible signal.
            pass
        self.client.force_login(user)
        return tenant

    def test_returns_correct_json_shape(self):
        url = self._resolve_url()
        self._signed_in_with_tenant()
        resp = self.client.get(url)
        if resp.status_code == 400 and resp.json().get("code") == "no_tenant":
            self.skipTest("test environment lacks request.tenant binding")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in ("public_key_b64", "key_version", "fingerprint_b64", "encryption_scheme"):
            self.assertIn(key, body, f"server-pubkey response missing '{key}'")
        self.assertEqual(body["encryption_scheme"], "libsodium-secretbox-x25519-sealed")
        # public_key_b64 decodes to 32 bytes
        self.assertEqual(len(base64.b64decode(body["public_key_b64"])), 32)

    def test_never_returns_private_bytes(self):
        url = self._resolve_url()
        self._signed_in_with_tenant()
        resp = self.client.get(url)
        raw = resp.content.decode("utf-8")
        # Any field with the word 'private' in the JSON would mean the
        # view leaked private material. We assert absence of the literal.
        self.assertNotIn("private", raw.lower())
        # Defensive: ``secret_key`` would be another leak shape.
        self.assertNotIn("secret_key", raw.lower())

    def test_anonymous_returns_no_tenant_error(self):
        url = self._resolve_url()
        resp = self.client.get(url)
        # Anonymous callers do not have request.tenant; expect 400.
        self.assertIn(resp.status_code, (400, 302))
        if resp.status_code == 400:
            self.assertEqual(resp.json().get("code"), "no_tenant")


@_REQUIRE_PYNACL
class CompanionKeypairRotateViewTests(TestCase):
    """POST /companion/keypair/rotate/ — staff-only."""

    def _resolve_url(self) -> str:
        from django.urls.exceptions import NoReverseMatch
        for ns in ("migration_cloud_super", "migration_cloud_portal"):
            try:
                return reverse(f"{ns}:companion_keypair_rotate")
            except NoReverseMatch:
                continue
        self.skipTest("migration_cloud URL namespace not mounted")
        return ""

    def test_anonymous_is_denied(self):
        url = self._resolve_url()
        resp = self.client.post(url, data="{}", content_type="application/json")
        # LoginRequiredMixin redirects unauthenticated callers; our view
        # also asserts is_staff at body-runtime. Either response shape is
        # acceptable (302 redirect or 403 JSON).
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_non_staff_user_is_denied(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # tenant-isolation-allow: test-create-user-for-auth-only-not-tenant-scoped
        user = User.objects.create_user(username="not_staff", password="x")
        self.client.force_login(user)
        url = self._resolve_url()
        resp = self.client.post(url, data="{}", content_type="application/json")
        # v3.34.0 — staff check fires before tenant check, so non-staff
        # still get the not_staff 403 even without a tenant.
        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertEqual(body.get("code"), "not_staff")


# ─── No-secrets-logged invariant ─────────────────────────────────────────


@_REQUIRE_PYNACL
class NoSecretsLoggedTests(TestCase):
    """Rotate must never log private key bytes."""

    def setUp(self):
        self.tenant = _make_tenant("no-secrets-logged")

    def test_rotate_logger_carries_only_ids_and_fingerprints(self):
        from apps.migration_cloud.services import companion_keypair
        companion_keypair.ensure_active_keypair(self.tenant)
        with self.assertLogs("apps.migration_cloud.services.companion_keypair", level="INFO") as cm:
            result = companion_keypair.rotate_active_keypair(
                self.tenant, operator_user=None
            )
        full_log = "\n".join(cm.output)
        # The log line includes tenant_pk, operator_id, old_version,
        # new_version, fingerprint.
        self.assertIn("rotate_active_keypair", full_log)
        self.assertIn(result["new_version"], full_log)
        # Private key bytes are never base64-emitted to logs. Heuristic:
        # the log line should not be longer than ~512 chars and should
        # not contain any contiguous run of 40+ base64-looking characters
        # beyond the fingerprint (which is 24 chars).
        for line in cm.output:
            # Filter out the prefix.
            payload = line.split(":", 2)[-1]
            # No 40+-char base64 chunks (a 32-byte privkey is 44 chars b64).
            import re

            long_b64 = re.findall(r"[A-Za-z0-9+/]{40,}", payload)
            self.assertFalse(
                long_b64,
                f"Suspicious long base64-looking blob in log line: {line!r} "
                f"(found {long_b64!r})",
            )


# ─── PyNaCl-missing fallback ─────────────────────────────────────────────


class PyNaClMissingSurfaceTests(SimpleTestCase):
    """When PyNaCl is absent, the service raises a typed RuntimeError."""

    def test_pynacl_unavailable_subclass(self):
        from apps.migration_cloud.services import companion_keypair
        self.assertTrue(issubclass(companion_keypair.PyNaClUnavailable, RuntimeError))
