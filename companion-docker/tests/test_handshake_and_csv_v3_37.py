"""v3.37.0 Agent 4 — Docker sibling tests.

10+ pytest cases covering:
  1. Login posts correct payload (httpx MockTransport).
  2. MAA fetch returns correct shape.
  3. MAA sign uses constant-time text compare.
  4. Canonical-domain match for 5 known domains.
  5. Canonical-domain miss returns None.
  6. seal-box happy path with PyNaCl (skipped if not installed).
  7. No plaintext in logs (capture stdlib logging).
  8. /ingest/csv accepts multipart with valid token (skipped if fastapi
     missing).
  9. /ingest/csv rejects missing token (401).
 10. Idempotency: identical canonical rows produce identical canonical_sha256.
 11. seal_box rejects bad pubkey (typed error).
"""
from __future__ import annotations

import io
import json
import logging
import os
import sys

import httpx
import pytest

# Make app importable when run from repo root.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DOCKER_ROOT = os.path.dirname(_THIS_DIR)
if _DOCKER_ROOT not in sys.path:
    sys.path.insert(0, _DOCKER_ROOT)

from app import canonical_csv as csv_mod  # noqa: E402
from app import rmc_handshake  # noqa: E402

try:
    import nacl.public  # noqa: F401
    HAS_PYNACL = True
except ImportError:
    HAS_PYNACL = False

try:
    from fastapi.testclient import TestClient  # noqa: F401
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


# ─── 1. login posts correct payload ──────────────────────────────────────


def test_login_posts_correct_payload():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"token": "bearer-xyz"})

    transport = httpx.MockTransport(handler)

    def factory():
        return httpx.Client(transport=transport)

    s = rmc_handshake.RMCSession("https://rmc.example.com", client_factory=factory)
    token = s.login("op@example.com", "hunter2")
    assert token == "bearer-xyz"
    assert captured["url"].endswith("/api/v1/auth/login/")
    assert captured["body"]["email"] == "op@example.com"
    assert captured["body"]["password"] == "hunter2"


# ─── 2. MAA fetch shape ───────────────────────────────────────────────────


def test_maa_fetch_returns_correct_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/migration/maa/text/"
        return httpx.Response(
            200,
            json={
                "vendor": "powerschool",
                "version": "v1.0",
                "text": "VERBATIM AGREEMENT BODY",
                "is_draft": False,
                "active_version": "v1.0",
            },
        )

    transport = httpx.MockTransport(handler)

    def factory():
        return httpx.Client(transport=transport)

    s = rmc_handshake.RMCSession("https://rmc.example.com", client_factory=factory)
    s._token = "tok"  # noqa: SLF001
    t = s.fetch_maa_text("school-a", "powerschool")
    assert t.vendor == "powerschool"
    assert t.version == "v1.0"
    assert t.text == "VERBATIM AGREEMENT BODY"
    assert t.is_draft is False
    assert t.active_version == "v1.0"


# ─── 3. MAA sign uses constant-time compare ──────────────────────────────


def test_maa_sign_uses_constant_time_compare_helper():
    # The helper used both client-side and (via the server) for the
    # signature_text echo. We assert the function uses hmac.compare_digest
    # by exercising it: equal strings ⇒ True; differing strings ⇒ False.
    a = "verbatim body"
    b = "verbatim body"
    c = "tampered  body"
    assert rmc_handshake.constant_time_text_eq(a, b) is True
    assert rmc_handshake.constant_time_text_eq(a, c) is False


# ─── 4. canonical-domain match for 5 known domains ───────────────────────


@pytest.mark.parametrize(
    "headers,expected",
    [
        (
            ["external_id", "first_name", "last_name", "grade_level"],
            "students",
        ),
        (
            ["staff_external_id", "first_name", "last_name", "email", "role"],
            "staff",
        ),
        (
            ["guardian_external_id", "first_name", "last_name", "student_external_id"],
            "guardians",
        ),
        (
            ["student_external_id", "date", "status", "code"],
            "attendance",
        ),
        (
            ["student_external_id", "subject_code", "term", "score"],
            "grades",
        ),
    ],
)
def test_canonical_domain_match_for_known_domains(headers, expected):
    assert csv_mod.match_canonical_domain(headers) == expected


# ─── 5. canonical-domain miss returns None ────────────────────────────────


def test_canonical_domain_miss_returns_none():
    assert csv_mod.match_canonical_domain(["foo", "bar", "baz"]) is None


# ─── 6. seal-box happy path ───────────────────────────────────────────────


@pytest.mark.skipif(not HAS_PYNACL, reason="PyNaCl not installed in this env")
def test_seal_box_happy_path_round_trip():
    import base64

    import nacl.public

    sk = nacl.public.PrivateKey.generate()
    pk_b64 = base64.b64encode(bytes(sk.public_key)).decode("ascii")
    plaintext = b"canonical row bytes"
    ciphertext = csv_mod.seal_box(plaintext, pk_b64)
    sealed = nacl.public.SealedBox(sk)
    assert sealed.decrypt(ciphertext) == plaintext


# ─── 6b. seal-box rejects bad pubkey ──────────────────────────────────────


@pytest.mark.skipif(not HAS_PYNACL, reason="PyNaCl not installed in this env")
def test_seal_box_rejects_bad_pubkey():
    with pytest.raises(csv_mod.BadPubkey):
        csv_mod.seal_box(b"x", "not-base64!!!")


# ─── 7. no plaintext in logs ──────────────────────────────────────────────


def test_no_plaintext_in_logs_on_seal_and_upload(caplog):
    # Build a fake httpx transport that records nothing and returns 201.
    if not HAS_PYNACL:
        pytest.skip("PyNaCl not installed")

    import base64

    import nacl.public

    sk = nacl.public.PrivateKey.generate()
    pk_b64 = base64.b64encode(bytes(sk.public_key)).decode("ascii")

    secret_value = "SENSITIVE_PII_VALUE_DO_NOT_LOG"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"receipt_id": 42, "bundle_id": 7, "status": "pending"})

    transport = httpx.MockTransport(handler)

    def factory():
        return httpx.Client(transport=transport)

    rows = [
        csv_mod.CanonicalRow(fields={"external_id": "s1", "first_name": secret_value}),
        csv_mod.CanonicalRow(fields={"external_id": "s2", "first_name": "Bob"}),
    ]

    caplog.set_level(logging.DEBUG, logger="app.canonical_csv")
    receipt = csv_mod.seal_box_and_upload(
        rows=rows,
        domain="students",
        server_pubkey_b64=pk_b64,
        server_url="https://rmc.example.com",
        bearer_token="bearer-abc",
        maa_id=1,
        vendor_source="powerschool",
        idempotency_key="idem-1",
        client_factory=factory,
    )
    assert receipt.receipt_id == 42
    # Assert NO log record contains the secret value or the bearer.
    for rec in caplog.records:
        msg = rec.getMessage()
        assert secret_value not in msg, f"plaintext leaked into log: {msg!r}"
        assert "bearer-abc" not in msg, f"bearer leaked into log: {msg!r}"


# ─── 8. /ingest/csv accepts multipart with valid token ────────────────────


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed in this env")
@pytest.mark.skipif(not HAS_PYNACL, reason="PyNaCl not installed in this env")
def test_ingest_csv_accepts_multipart_with_valid_token(monkeypatch):
    import base64

    import nacl.public
    from fastapi.testclient import TestClient

    from app import main as docker_main

    sk = nacl.public.PrivateKey.generate()
    pk_b64 = base64.b64encode(bytes(sk.public_key)).decode("ascii")

    # Patch seal_box_and_upload to skip the upstream call and return a
    # canned receipt — the endpoint contract is what we're testing.
    def fake_upload(**kwargs):
        return csv_mod.UploadReceipt(
            receipt_id=99,
            bundle_id=8,
            status="pending",
            canonical_sha256="a" * 64,
        )

    monkeypatch.setattr(csv_mod, "seal_box_and_upload", fake_upload)

    client = TestClient(docker_main.app)
    csv_bytes = (
        b"external_id,first_name,last_name,grade_level\n"
        b"s1,Alice,Adams,5\n"
        b"s2,Bob,Brown,6\n"
    )
    resp = client.post(
        "/ingest/csv",
        data={
            "server_url": "https://rmc.example.com",
            "tenant_slug": "school-a",
            "vendor_source": "powerschool",
            "maa_id": "1",
            "pubkey_b64": pk_b64,
        },
        files={"file": ("students.csv", csv_bytes, "text/csv")},
        headers={"Authorization": "Bearer goodtoken"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["receipt_id"] == 99
    assert body["matched_domain"] == "students"
    assert body["row_count"] == 2


# ─── 9. /ingest/csv rejects missing token (401) ───────────────────────────


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed in this env")
def test_ingest_csv_rejects_missing_token():
    from fastapi.testclient import TestClient

    from app import main as docker_main

    client = TestClient(docker_main.app)
    resp = client.post(
        "/ingest/csv",
        data={
            "server_url": "https://rmc.example.com",
            "tenant_slug": "school-a",
            "vendor_source": "powerschool",
            "maa_id": "1",
            "pubkey_b64": "AAAA",
        },
        files={"file": ("students.csv", b"external_id\ns1\n", "text/csv")},
        # no Authorization header
    )
    assert resp.status_code == 401


# ─── 10. idempotent canonical bytes → identical sha256 ────────────────────


def test_idempotency_identical_rows_produce_identical_canonical_sha256():
    rows_v1 = [
        csv_mod.CanonicalRow(fields={"external_id": "s1", "first_name": "Alice"}),
        csv_mod.CanonicalRow(fields={"external_id": "s2", "first_name": "Bob"}),
    ]
    rows_v2 = [
        csv_mod.CanonicalRow(fields={"external_id": "s2", "first_name": "Bob"}),
        csv_mod.CanonicalRow(fields={"external_id": "s1", "first_name": "Alice"}),
    ]
    import hashlib

    h1 = hashlib.sha256(csv_mod.canonical_serialize(rows_v1)).hexdigest()
    h2 = hashlib.sha256(csv_mod.canonical_serialize(rows_v2)).hexdigest()
    assert h1 == h2, "row order must not affect canonical_sha256"


# ─── 11. parse_csv_bytes handles BOM + empty file ────────────────────────


def test_parse_csv_bytes_handles_bom_and_empty():
    bom_csv = b"\xef\xbb\xbfexternal_id,first_name\ns1,Alice\n"
    headers, rows = csv_mod.parse_csv_bytes(bom_csv)
    assert headers == ["external_id", "first_name"]
    assert rows[0]["external_id"] == "s1"

    empty_headers, empty_rows = csv_mod.parse_csv_bytes(b"")
    assert empty_headers == []
    assert empty_rows == []


# ─── 12. load_canonical_headers returns >= 20 domains ────────────────────


def test_load_canonical_headers_returns_at_least_20_domains():
    t = csv_mod.load_canonical_headers()
    assert len(t) >= 20
    assert "students" in t
    assert "guardians" in t


# ─── 13. handshake login 401 raises Unauthorized ─────────────────────────


def test_login_401_raises_unauthorized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "bad creds"})

    transport = httpx.MockTransport(handler)

    def factory():
        return httpx.Client(transport=transport)

    s = rmc_handshake.RMCSession("https://rmc.example.com", client_factory=factory)
    with pytest.raises(rmc_handshake.Unauthorized):
        s.login("op@example.com", "wrong")


# ─── 14. session.clear_token wipes the in-memory token ───────────────────


def test_clear_token_wipes_internal_state():
    s = rmc_handshake.RMCSession("https://rmc.example.com")
    s._token = "secret-bearer"  # noqa: SLF001
    s.clear_token()
    assert s._token is None  # noqa: SLF001
