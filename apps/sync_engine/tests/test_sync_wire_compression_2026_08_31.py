"""G6: nothing on the sync wire was compressed, in either direction.

``GZipMiddleware`` is absent from ``config/settings.py`` and the box's own requests never
sent ``Accept-Encoding`` (the header dicts in ``edge_outbox.pull_bundle`` and
``edge_outbox.post_bundle``). Bundles are NDJSON — one repeated JSON object shape per
line — so this is the most compressible payload the platform moves, on the link a village
school pays for by the megabyte.

THE TRAP THIS FILE IS MOSTLY ABOUT. ``urllib`` does not decode a compressed response. A
client that sends ``Accept-Encoding: gzip`` and then reads ``resp.read()`` gets gzip bytes
and hands them to ``verify_and_parse_bundle``, whose first line is
``data.decode("utf-8")``. Asking for compression without decoding it does not make sync
slower — it corrupts every bundle. ``test_a_compressed_response_decodes_to_identical_bytes``
is the proof that both halves are present, and it asserts BYTE IDENTITY rather than "it
parsed", because a bundle is HMAC-signed over its plaintext and near-enough is not a
signature.

The upload direction is a request BODY, which HTTP gives a client no way to negotiate. So
the cloud ADVERTISES that it decodes one, on responses the box was already reading, and
the box compresses only after it has seen the advert — with a one-shot uncompressed retry
for the case where the advert was stale.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import uuid
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.academics.models import AcademicYear
from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleDownloadView, SyncBundleUploadView
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import export_delta_bundle, verify_and_parse_bundle

_SIGN_KEY = "g6-compression-test-key"
_ACCEPT_ADVERT = "X-RMC-Sync-Accept-Encoding"
_LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "g6-wire-compression",
    }
}


class _FakeResponse:
    """Just enough of ``http.client.HTTPResponse`` for ``urllib.request.urlopen``."""

    def __init__(self, body, headers, code=200):
        self._body = body
        self.headers = headers
        self._code = code

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body

    def getcode(self):
        return self._code


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY, CACHES=_LOCMEM)
class DownloadCompressesTheBundleTests(TestCase):
    """Cloud -> box. The bundle is the biggest body on the rail."""

    def setUp(self):
        cache.clear()
        uid = uuid.uuid4().hex[:8]
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name=f"Zip {uid}", slug=f"zip-{uid}", subdomain=f"zip{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"zip_admin_{uid}", password="Test1234", email=f"z{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        # Enough near-identical rows that gzip has something to work with — which is
        # exactly the real shape: one repeated object per line.
        for i in range(40):
            AcademicYear.objects.create(
                school=self.school,
                name=f"Academic Year {2000 + i} to {2001 + i}",
                start_date=dt.date(2000 + i, 9, 1),
                end_date=dt.date(2001 + i, 6, 30),
            )
        self.rf = APIRequestFactory()

    def _download(self, **extra):
        request = self.rf.get("/api/v1/sync/bundle/download/", **extra)
        request.school = self.school
        force_authenticate(request, user=self.user)
        return SyncBundleDownloadView.as_view()(request)

    def _payload(self, resp):
        return resp.getvalue() if hasattr(resp, "getvalue") else resp.content

    def test_a_box_that_asks_for_gzip_gets_gzip(self):
        resp = self._download(HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get("Content-Encoding"),
            "gzip",
            "the bundle went out uncompressed although the box asked for gzip — this is "
            "the whole of G6 on the download leg",
        )

    def test_the_compressed_bundle_is_a_valid_bundle_and_is_smaller(self):
        """Compared by CONTENT, not byte-for-byte across two responses.

        ``export_delta_bundle`` mints a fresh replay ``nonce`` per BUILD (deliberately —
        it is what lets a legitimate retry through while a captured replay is refused),
        so two downloads of the same delta are never byte-identical to each other. Byte
        identity is proved where it can be, in
        ``test_a_compressed_response_decodes_to_identical_bytes``, against one fixed
        bundle carried across the wire.
        """
        plain = self._payload(self._download())
        packed = self._payload(self._download(HTTP_ACCEPT_ENCODING="gzip"))
        inflated = gzip.decompress(packed)

        plain_rows, plain_errors = verify_and_parse_bundle(
            plain, expected_school_id=self.school.id
        )
        packed_rows, packed_errors = verify_and_parse_bundle(
            inflated, expected_school_id=self.school.id
        )
        self.assertEqual(plain_errors, [])
        self.assertEqual(packed_errors, [], "the inflated body did not verify")
        self.assertEqual(
            sorted((r["entity_type"], str(r["id"])) for r in packed_rows),
            sorted((r["entity_type"], str(r["id"])) for r in plain_rows),
        )
        self.assertLess(
            len(packed),
            len(inflated),
            "compression made the NDJSON bundle no smaller",
        )

    def test_a_box_that_does_not_ask_gets_plain_bytes(self):
        resp = self._download()
        self.assertIsNone(resp.get("Content-Encoding"))
        rows, errors = verify_and_parse_bundle(
            self._payload(resp), expected_school_id=self.school.id
        )
        self.assertEqual(errors, [])
        self.assertTrue(rows)

    def test_the_response_varies_on_accept_encoding(self):
        """A cache that keys without this serves a gzip body to a client that cannot
        read it, and a plain body to one that asked for gzip."""
        resp = self._download(HTTP_ACCEPT_ENCODING="gzip")
        self.assertIn("accept-encoding", (resp.get("Vary") or "").lower())

    def test_q0_is_a_refusal_not_a_request(self):
        resp = self._download(HTTP_ACCEPT_ENCODING="gzip;q=0")
        self.assertIsNone(resp.get("Content-Encoding"))

    def test_the_download_advertises_that_it_decodes_uploads(self):
        """The box cannot negotiate a request body's encoding, so this header is the
        only way it can ever learn that compressing its push is safe."""
        self.assertEqual(self._download().get(_ACCEPT_ADVERT), "gzip")

    def test_the_switch_restores_the_previous_wire(self):
        with override_settings(RMC_SYNC_WIRE_COMPRESSION_ENABLED=False):
            resp = self._download(HTTP_ACCEPT_ENCODING="gzip")
        self.assertIsNone(resp.get("Content-Encoding"))
        self.assertIsNone(resp.get(_ACCEPT_ADVERT))


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY, CACHES=_LOCMEM)
class BoxDecodesWhatItAsksForTests(TestCase):
    """``pull_bundle`` must inflate the answer. urllib will not do it."""

    def setUp(self):
        cache.clear()
        uid = uuid.uuid4().hex[:8]
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name=f"Pullz {uid}", slug=f"pullz-{uid}", subdomain=f"pullz{uid}", is_active=True
        )
        self.bundle = export_delta_bundle(
            school_id=str(self.school.id),
            rows=[
                {
                    "entity_type": "student",
                    "id": i,
                    "client_offline_id": "",
                    "changes": {"first_name": "Ada", "last_name": "Njoya"},
                    "updated_at": timezone.now().isoformat(),
                }
                for i in range(30)
            ],
            device_id="cloud",
        )

    def test_the_pull_asks_for_compression(self):
        from apps.sync_engine import edge_outbox

        seen = {}

        def _urlopen(req, timeout=None):
            seen["headers"] = dict(req.headers)
            return _FakeResponse(self.bundle, {})

        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            edge_outbox.pull_bundle("https://hub.test/api/v1/sync/bundle/download/", "tok")
        # urllib title-cases header keys on Request.
        accept = {k.lower(): v for k, v in seen["headers"].items()}.get("accept-encoding")
        self.assertEqual(
            accept, "gzip", "the box never asked for compression on the biggest body it moves"
        )

    def test_a_compressed_response_decodes_to_identical_bytes(self):
        """THE round trip. Byte identity, because the bundle is signed over plaintext."""
        from apps.sync_engine import edge_outbox

        packed = gzip.compress(self.bundle, mtime=0)

        def _urlopen(req, timeout=None):
            return _FakeResponse(packed, {"Content-Encoding": "gzip"})

        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            status, body, _hw = edge_outbox.pull_bundle(
                "https://hub.test/api/v1/sync/bundle/download/", "tok"
            )

        self.assertEqual(status, 200)
        self.assertEqual(
            body,
            self.bundle,
            "the box handed gzip bytes to the bundle verifier — asking for compression "
            "without decoding it does not slow sync down, it corrupts every bundle",
        )
        rows, errors = verify_and_parse_bundle(body, expected_school_id=self.school.id)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 30)

    def test_an_uncompressed_response_is_passed_through_untouched(self):
        from apps.sync_engine import edge_outbox

        def _urlopen(req, timeout=None):
            return _FakeResponse(self.bundle, {})

        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            _status, body, _hw = edge_outbox.pull_bundle(
                "https://hub.test/api/v1/sync/bundle/download/", "tok"
            )
        self.assertEqual(body, self.bundle)

    def test_the_end_to_end_round_trip_through_the_real_view(self):
        """Serve a real gzipped response from the real endpoint, read it with the real
        client, and require the plaintext back."""
        from apps.sync_engine import edge_outbox

        user = User.objects.create_superuser(
            username=f"e2e_{uuid.uuid4().hex[:8]}", password="Test1234", email="e2e@test.com"
        )
        SchoolMembership.objects.create(
            user=user, school=self.school, role="ADMIN", is_primary=True
        )
        for i in range(25):
            AcademicYear.objects.create(
                school=self.school,
                name=f"Round Trip Year {2000 + i}",
                start_date=dt.date(2000 + i, 9, 1),
                end_date=dt.date(2001 + i, 6, 30),
            )
        rf = APIRequestFactory()

        def _serve(accept_encoding):
            request = rf.get(
                "/api/v1/sync/bundle/download/", HTTP_ACCEPT_ENCODING=accept_encoding
            )
            request.school = self.school
            force_authenticate(request, user=user)
            resp = SyncBundleDownloadView.as_view()(request)
            payload = resp.getvalue() if hasattr(resp, "getvalue") else resp.content
            return resp, payload

        gz_resp, packed = _serve("gzip")
        self.assertEqual(gz_resp.get("Content-Encoding"), "gzip")
        # What the SERVER put on the wire for THIS response. Comparing against a second
        # download would compare two different builds: the bundle carries a fresh replay
        # nonce every time it is built.
        expected = gzip.decompress(packed)

        def _urlopen(req, timeout=None):
            return _FakeResponse(packed, dict(gz_resp.headers.items()))

        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            _status, body, _hw = edge_outbox.pull_bundle(
                "https://hub.test/api/v1/sync/bundle/download/", "tok"
            )
        self.assertEqual(
            body,
            expected,
            "the box did not reproduce the exact bytes the cloud signed",
        )
        rows, errors = verify_and_parse_bundle(body, expected_school_id=self.school.id)
        self.assertEqual(errors, [], "the signature did not survive the round trip")
        self.assertTrue(rows)
        self.assertLess(len(packed), len(expected))


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY, CACHES=_LOCMEM)
class UploadAcceptsACompressedBodyTests(TestCase):
    """Box -> cloud. The push body is the other half of "end to end"."""

    def setUp(self):
        cache.clear()
        uid = uuid.uuid4().hex[:8]
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name=f"Up {uid}", slug=f"up-{uid}", subdomain=f"up{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"up_admin_{uid}", password="Test1234", email=f"u{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="Before",
            start_date=dt.date(2024, 9, 1),
            end_date=dt.date(2025, 6, 30),
        )
        from apps.api.sync_services import _get_entity_config

        self.entity = next(
            k
            for k, (model, _a) in _get_entity_config(include_derived=True).items()
            if model is AcademicYear
        )
        self.bundle = export_delta_bundle(
            school_id=str(self.school.id),
            rows=[
                {
                    "entity_type": self.entity,
                    "id": self.year.pk,
                    "client_offline_id": "",
                    "changes": {"name": "After"},
                    "updated_at": (timezone.now() + dt.timedelta(hours=1)).isoformat(),
                }
            ],
            device_id="edge",
        )
        self.rf = APIRequestFactory()

    def _upload(self, payload, **extra):
        request = self.rf.post(
            "/api/v1/sync/bundle/upload/",
            data=payload,
            content_type="application/x-rmc-sync-bundle+ndjson",
            **extra,
        )
        request.school = self.school
        force_authenticate(request, user=self.user)
        resp = SyncBundleUploadView.as_view()(request)
        resp.render()
        return resp

    def test_a_gzip_body_is_decoded_and_applied(self):
        resp = self._upload(
            gzip.compress(self.bundle, mtime=0), HTTP_CONTENT_ENCODING="gzip"
        )
        self.assertEqual(
            resp.status_code,
            200,
            f"the operator could not read a gzipped push body: {resp.content[:300]!r}",
        )
        body = json.loads(resp.content)
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body.get("received"), 1)
        self.year.refresh_from_db()
        self.assertEqual(self.year.name, "After")

    def test_a_plain_body_still_works(self):
        resp = self._upload(self.bundle)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content).get("ok"))

    def test_the_upload_advertises_that_it_decodes_uploads(self):
        self.assertEqual(self._upload(self.bundle).get(_ACCEPT_ADVERT), "gzip")

    def test_the_answer_comes_back_compressed_when_the_box_asks(self):
        """The receiver's reply carries a ``results`` entry per row, so on a full page it
        is the larger half of the exchange — on the link the school is paying for."""
        rows = [
            {
                "entity_type": self.entity,
                "id": self.year.pk,
                "client_offline_id": "",
                "changes": {"name": f"Bulk {i}"},
                "updated_at": (timezone.now() + dt.timedelta(hours=1, seconds=i)).isoformat(),
            }
            for i in range(60)
        ]
        # TWO bundles, not one sent twice: the replay guard keys on the bundle nonce and
        # would answer the second presentation with a 409, which is correct and would
        # make this assert about the wrong response.
        plain = self._upload(
            export_delta_bundle(
                school_id=str(self.school.id), rows=rows, device_id="edge"
            )
        )
        self.assertEqual(plain.status_code, 200, plain.content[:300])
        packed = self._upload(
            export_delta_bundle(
                school_id=str(self.school.id), rows=rows, device_id="edge"
            ),
            HTTP_ACCEPT_ENCODING="gzip",
        )
        self.assertEqual(
            packed.get("Content-Encoding"),
            "gzip",
            "the receiver's per-row answer went back uncompressed",
        )
        self.assertLess(len(packed.content), len(plain.content))

    def test_a_decompression_bomb_is_refused_rather_than_inflated(self):
        """An authenticated box is still an untrusted source of a compression ratio."""
        bomb = gzip.compress(b"A" * (2 * 1024 * 1024), mtime=0)
        with override_settings(RMC_SYNC_MAX_DECOMPRESSED_BUNDLE_BYTES=1024):
            resp = self._upload(bomb, HTTP_CONTENT_ENCODING="gzip")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("too_large", resp.content.decode())

    def test_a_corrupt_gzip_body_is_a_400_not_a_500(self):
        resp = self._upload(b"not actually gzip at all", HTTP_CONTENT_ENCODING="gzip")
        self.assertEqual(resp.status_code, 400)

    def test_an_unknown_content_encoding_is_refused(self):
        resp = self._upload(self.bundle, HTTP_CONTENT_ENCODING="br")
        self.assertEqual(resp.status_code, 400)


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY, CACHES=_LOCMEM)
class BoxCompressesOnlyWhatItIsToldToTests(TestCase):
    """The box must never GUESS that an operator decodes a gzip body.

    An operator that predates this hands the bytes to ``verify_and_parse_bundle``, which
    does ``data.decode("utf-8")`` and RAISES — so an unconditional gzip push would turn
    every cycle on an un-upgraded cloud into a 500.
    """

    def setUp(self):
        cache.clear()
        self.endpoint = "https://hub.test/api/v1/sync/bundle/upload/"
        self.data = b"line-one\nline-two\n" * 200

    def _post(self, responder):
        from apps.sync_engine import edge_outbox

        with mock.patch("urllib.request.urlopen", side_effect=responder):
            return edge_outbox.post_bundle(self.endpoint, "tok", self.data)

    def test_without_an_advert_the_body_goes_up_uncompressed(self):
        sent = []

        def _urlopen(req, timeout=None):
            sent.append((req.data, dict(req.headers)))
            return _FakeResponse(b'{"ok": true}', {})

        self._post(_urlopen)
        payload, headers = sent[0]
        self.assertEqual(payload, self.data)
        self.assertNotIn(
            "gzip",
            str({k.lower(): v for k, v in headers.items()}.get("content-encoding") or ""),
        )

    def test_after_the_advert_the_body_is_compressed(self):
        from apps.sync_engine import compression

        compression.remember_peer_accepts_gzip(self.endpoint, True)
        sent = []

        def _urlopen(req, timeout=None):
            sent.append((req.data, dict(req.headers)))
            return _FakeResponse(b'{"ok": true}', {})

        self._post(_urlopen)
        payload, headers = sent[0]
        lowered = {k.lower(): v for k, v in headers.items()}
        self.assertEqual(lowered.get("content-encoding"), "gzip")
        self.assertEqual(gzip.decompress(payload), self.data)
        self.assertLess(len(payload), len(self.data))

    def test_the_advert_is_learned_from_a_download_response(self):
        """It rides a response the box was already reading — no extra round trip."""
        from apps.sync_engine import compression, edge_outbox

        download = "https://hub.test/api/v1/sync/bundle/download/"

        def _urlopen(req, timeout=None):
            return _FakeResponse(b"", {_ACCEPT_ADVERT: "gzip"})

        with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
            edge_outbox.pull_bundle(download, "tok")
        self.assertTrue(compression.peer_accepts_gzip(self.endpoint))

    def test_a_rejected_compressed_push_falls_back_and_forgets_the_advert(self):
        """The advert can be stale — a cloud rolled BACK between learning it and using
        it. Re-sending the SAME bytes is safe against a double apply because the replay
        guard keys on the bundle nonce."""
        import urllib.error

        from apps.sync_engine import compression

        compression.remember_peer_accepts_gzip(self.endpoint, True)
        attempts = []

        def _urlopen(req, timeout=None):
            attempts.append((req.data, dict(req.headers)))
            if len(attempts) == 1:
                raise urllib.error.HTTPError(
                    self.endpoint, 400, "Bad Request", {}, None
                )
            return _FakeResponse(b'{"ok": true}', {})

        status, body = self._post(_urlopen)
        self.assertEqual(len(attempts), 2, "no uncompressed retry after a gzip rejection")
        self.assertEqual(attempts[1][0], self.data, "the retry was not the plain body")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))
        self.assertFalse(
            compression.peer_accepts_gzip(self.endpoint),
            "a stale advert survived the rejection it caused",
        )

    def test_a_401_is_not_retried_uncompressed(self):
        """A decision about the bundle. Re-sending it would only repeat the decision."""
        import urllib.error

        from apps.sync_engine import compression

        compression.remember_peer_accepts_gzip(self.endpoint, True)
        attempts = []

        def _urlopen(req, timeout=None):
            attempts.append(req.data)
            raise urllib.error.HTTPError(self.endpoint, 401, "Unauthorized", {}, None)

        status, _body = self._post(_urlopen)
        self.assertEqual(status, 401)
        self.assertEqual(len(attempts), 1)
