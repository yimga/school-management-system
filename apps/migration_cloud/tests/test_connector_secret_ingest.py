"""T15 gap #1: secure connector-credential capture + handle reconstruction.

The connector intake methods (API_PULL / OAUTH_FOLDER) need live credentials
(bearer / OAuth access token) to pull artifacts. Those are captured on the
attach-source form and stored in ``MigrationBundle.connector_secret``, a
Fernet-encrypted-at-rest field. ``pipeline.build_connector_handle`` reconstructs
the adapter handle from that (decrypted) secret at ingest, and a new Phase-U1
step in ``advance_bundle`` pulls the artifacts before profiling.

Security-critical assertions here:
  * The token round-trips through the ORM (decrypts on read) …
  * … but is NOT present in clear text in the raw DB column (encrypted at rest).
  * The attach-source view captures the token into the encrypted field.
Plus the handle-reconstruction logic per method.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.pipeline import build_connector_handle

_TABLE = "migration_cloud_migrationbundle"


def _operator():
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="ops-connsecret@example.com",
        defaults={
            "email": "ops-connsecret@example.com",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    user.set_password("x")
    user.save()
    return user


def _raw_connector_secret(pk: int) -> str:
    with connection.cursor() as cur:
        cur.execute(f"SELECT connector_secret FROM {_TABLE} WHERE id = %s", [pk])  # noqa: S608 — constant table name
        row = cur.fetchone()
    return row[0] if row else ""


class ConnectorSecretEncryptionTests(TestCase):
    def test_secret_round_trips_but_is_encrypted_at_rest(self):
        token = "super-secret-vendor-token-abc123XYZ"
        bundle = MigrationBundle.objects.create(
            label="api bundle",
            intake_method=IntakeMethod.API_PULL,
            idempotency_key="conn-secret-round-trip",
            status=BundleStatus.PENDING,
        )
        bundle.connector_secret = {
            "url": "https://api.vendor/export",
            "api_token": token,
            "artifact_name": "students.json",
        }
        bundle.save(update_fields=["connector_secret"])

        # Round-trips via the ORM (decrypts on read).
        reloaded = MigrationBundle.objects.get(pk=bundle.pk)
        self.assertEqual(reloaded.connector_secret["api_token"], token)

        # …but the raw column must NOT contain the plaintext token.
        raw = _raw_connector_secret(bundle.pk)
        self.assertNotIn(token, raw)
        self.assertNotEqual(raw, "{}")  # something WAS stored (ciphertext)

    def test_empty_secret_costs_no_ciphertext(self):
        bundle = MigrationBundle.objects.create(
            label="plain upload",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="conn-secret-empty",
        )
        raw = _raw_connector_secret(bundle.pk)
        # An empty dict takes EncryptedJSONField's unencrypted fast-path: a tiny
        # marker (the literal "{}"), NEVER a Fernet token — those base64-encode to
        # a long "gAAAA…" blob. So an unattached bundle carries no ciphertext cost.
        self.assertNotIn("gAAAA", raw)
        self.assertLessEqual(len(raw), 8)

    def test_reloaded_empty_secret_never_crashes_handle(self):
        """Regression guard: the empty fast-path reloads as the STRING "{}", not a
        dict, so build_connector_handle must coerce defensively. advance_bundle
        always reloads the bundle, so a naive dict(secret) would crash the pipeline
        for every connector bundle that has no credentials attached yet.
        """
        for method in (
            IntakeMethod.API_PULL,
            IntakeMethod.OAUTH_FOLDER,
            IntakeMethod.DATABASE,
            IntakeMethod.FILE_UPLOAD,
        ):
            bundle = MigrationBundle.objects.create(
                label=f"empty {method}",
                intake_method=method,
                idempotency_key=f"conn-secret-reload-{method}",
            )
            reloaded = MigrationBundle.objects.get(pk=bundle.pk)
            # The stored value is the literal string "{}" after a round-trip.
            self.assertEqual(reloaded.connector_secret, "{}")
            # Must NOT raise (was ValueError: dict("{}")); no creds → no handle.
            self.assertIsNone(build_connector_handle(reloaded))


class BuildConnectorHandleTests(TestCase):
    def test_api_pull_handle(self):
        bundle = MigrationBundle.objects.create(
            label="api",
            intake_method=IntakeMethod.API_PULL,
            idempotency_key="conn-handle-api",
            intake_source_uri="https://api.vendor/export",
            connector_secret={
                "url": "https://api.vendor/export",
                "api_token": "tok",
                "artifact_name": "s.json",
            },
        )
        self.assertEqual(
            build_connector_handle(bundle),
            {"url": "https://api.vendor/export", "api_token": "tok", "artifact_name": "s.json"},
        )

    def test_api_pull_without_token_returns_none(self):
        bundle = MigrationBundle.objects.create(
            label="api-no-token",
            intake_method=IntakeMethod.API_PULL,
            idempotency_key="conn-handle-api-none",
            intake_source_uri="https://api.vendor/export",
        )
        # No secret captured yet → None → Phase-U1 cleanly skips (no crash).
        self.assertIsNone(build_connector_handle(bundle))

    def test_oauth_handle(self):
        bundle = MigrationBundle.objects.create(
            label="oauth",
            intake_method=IntakeMethod.OAUTH_FOLDER,
            idempotency_key="conn-handle-oauth",
            connector_secret={
                "provider": "google_drive",
                "folder_id": "FOLDER1",
                "access_token": "AT",
            },
        )
        self.assertEqual(
            build_connector_handle(bundle),
            {"provider": "google_drive", "folder_id": "FOLDER1", "access_token": "AT"},
        )

    def test_database_handle_is_the_uri_path(self):
        bundle = MigrationBundle.objects.create(
            label="db",
            intake_method=IntakeMethod.DATABASE,
            idempotency_key="conn-handle-db",
            intake_source_uri="/data/legacy.sqlite3",
        )
        self.assertEqual(build_connector_handle(bundle), "/data/legacy.sqlite3")

    def test_file_upload_has_no_connector_handle(self):
        bundle = MigrationBundle.objects.create(
            label="upload",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="conn-handle-upload",
            intake_source_uri="students.csv",
        )
        # FILE_UPLOAD is not a connector method → None (advance profiles the
        # already-ingested artifacts instead).
        self.assertIsNone(build_connector_handle(bundle))


class AttachSourceCaptureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)

    def test_attach_source_captures_token_encrypted(self):
        bundle = MigrationBundle.objects.create(
            label="api view",
            intake_method=IntakeMethod.API_PULL,
            idempotency_key="conn-attach-view",
            status=BundleStatus.PENDING,
        )
        url = reverse(
            "migration_cloud_super:bundle_attach_source", kwargs={"bundle_id": bundle.pk}
        )
        token = "view-captured-token-xyz789QQ"
        resp = self.client.post(
            url,
            data={
                "intake_source_uri": "https://api.vendor/export",
                "api_token": token,
                "artifact_name": "roster.json",
                "notes": "vendor export",
            },
        )
        self.assertIn(resp.status_code, (302, 303), resp.content)

        bundle.refresh_from_db()
        self.assertEqual(bundle.connector_secret.get("api_token"), token)
        self.assertEqual(bundle.connector_secret.get("artifact_name"), "roster.json")
        # Encrypted at rest — raw column has no plaintext token.
        self.assertNotIn(token, _raw_connector_secret(bundle.pk))
