"""Canonical-CSV ingest (v3.37.0 Agent 4 — Docker sibling).

Mirrors `companion-tauri/src-tauri/src/canonical_csv.rs`. Operator
manually exports CSV from their SIS via the SIS's OWN export UI;
this module parses, matches against canonical headers, seals with
libsodium, and uploads to the RMC platform.

This module NEVER calls a third-party SIS. The only network calls
target the RMC platform's own `/api/v1/migration/companion/upload/`
endpoint.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import logging
import os
import uuid
from typing import Any, Iterable, Optional

import httpx

from . import extractors as _extractors

logger = logging.getLogger(__name__)

# Locate the canonical-headers JSON shipped alongside this module.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CANONICAL_HEADERS_PATH = os.path.join(_THIS_DIR, "canonical_headers.json")

# Mirrors HEADER_MATCH_MIN_HITS in apps/migration_cloud/accelerators/runmycampus_canonical.py.
HEADER_MATCH_MIN_HITS = 3


class CsvIngestError(Exception):
    """Typed canonical-CSV error."""


class NotFoundError(CsvIngestError):
    pass


class ParseError(CsvIngestError):
    pass


class CanonicalTableCorrupt(CsvIngestError):
    pass


class SealFailed(CsvIngestError):
    pass


class BadPubkey(CsvIngestError):
    pass


class UploadRejected(CsvIngestError):
    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message or f"upload rejected status={status}")
        self.status = status


@dataclasses.dataclass
class CanonicalRow:
    fields: dict[str, str]


@dataclasses.dataclass
class UploadReceipt:
    receipt_id: int
    bundle_id: Optional[int]
    status: str
    canonical_sha256: str


def load_canonical_headers() -> dict[str, list[str]]:
    """Load the canonical domain → headers map from the bundled JSON."""
    try:
        with open(_CANONICAL_HEADERS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as exc:
        raise CanonicalTableCorrupt(f"failed to load canonical_headers.json: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise CanonicalTableCorrupt("canonical_headers.json must be an object")
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        if not isinstance(v, list) or not all(isinstance(s, str) for s in v):
            raise CanonicalTableCorrupt(f"domain {k} headers must be list[str]")
        out[k] = list(v)
    return out


def parse_csv_bytes(blob: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a CSV from in-memory bytes (preferred for streaming)."""
    try:
        text = blob.decode("utf-8-sig")  # tolerate BOM from Excel exports
    except UnicodeDecodeError as exc:
        raise ParseError(f"csv decode failed: {type(exc).__name__}") from exc
    reader = csv.reader(io.StringIO(text))
    try:
        header_row = next(reader)
    except StopIteration:
        return ([], [])
    headers = [h.strip() for h in header_row]
    rows: list[dict[str, str]] = []
    for record in reader:
        row: dict[str, str] = {}
        for i, cell in enumerate(record):
            if i < len(headers):
                row[headers[i]] = cell
        rows.append(row)
    return (headers, rows)


def parse_csv(path: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a CSV from disk path."""
    if not os.path.isfile(path):
        raise NotFoundError(f"csv not found: {path}")
    with open(path, "rb") as fh:
        return parse_csv_bytes(fh.read())


def parse_and_preprocess(
    path: str,
) -> tuple[Optional[str], list[str], list[dict[str, str]]]:
    """Parse a CSV file AND apply vendor pre-processing.

    Pipeline:
      1. ``parse_csv(path)`` → (headers, raw rows).
      2. ``extractors.detect_vendor(headers)`` → optional vendor name.
      3. ``extractors.preprocess_for_vendor(vendor, rows)`` → vendor
         normalization (date formats, header casing, status codes,
         role partitioning, JSON-in-cell). Unknown vendor → identity.

    Returns ``(detected_vendor, headers, processed_rows)``. Downstream
    callers continue with ``match_canonical_domain`` + ``canonicalize_row``.
    """
    headers, rows = parse_csv(path)
    vendor = _extractors.detect_vendor(headers)
    processed = _extractors.preprocess_for_vendor(vendor, rows)
    if vendor is not None:
        # Recompute headers from the union of processed-row keys.
        seen: set[str] = set()
        new_headers: list[str] = []
        for r in processed:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    new_headers.append(k)
        new_headers.sort()
        return (vendor, new_headers, processed)
    return (vendor, headers, processed)


def match_canonical_domain(headers: Iterable[str]) -> Optional[str]:
    """Header-only domain match. Returns the canonical domain name with
    the highest overlap above HEADER_MATCH_MIN_HITS, or None.
    """
    table = load_canonical_headers()
    norm_in = [h.strip().lower() for h in headers]
    best: Optional[tuple[str, int]] = None
    for domain in sorted(table.keys()):  # deterministic tie-break
        canon_lower = [c.lower() for c in table[domain]]
        hits = sum(1 for h in norm_in if h in canon_lower)
        if hits >= HEADER_MATCH_MIN_HITS:
            if best is None or hits > best[1]:
                best = (domain, hits)
    return best[0] if best else None


def canonicalize_row(row: dict[str, str], domain: str) -> CanonicalRow:
    # Header-match only — values pass through verbatim. The server
    # mapper handles case normalization + routing unknowns to custom_fields.
    del domain  # signature parity with rust sibling; unused here
    return CanonicalRow(fields=dict(row))


def canonical_serialize(rows: list[CanonicalRow]) -> bytes:
    """Produce deterministic bytes from canonical rows.

    Same rows in any order → same bytes (sorted by external_id-like
    column, then JSON with sort_keys=True).
    """
    id_keys = [
        "external_id",
        "student_external_id",
        "staff_external_id",
        "guardian_external_id",
        "section_external_id",
        "recipient_external_id",
        "item_external_id",
        "subject_external_id",
        "reference",
    ]

    def sort_key(r: CanonicalRow) -> tuple[int, str]:
        for k in id_keys:
            if k in r.fields:
                return (0, r.fields[k])
        return (1, "")

    sorted_rows = sorted(rows, key=sort_key)
    payload = [dict(r.fields) for r in sorted_rows]
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


def seal_box(plaintext: bytes, server_pubkey_b64: str) -> bytes:
    """libsodium crypto_box_seal (X25519 + XSalsa20-Poly1305).

    Raises BadPubkey if the base64 doesn't decode to 32 bytes; raises
    SealFailed if PyNaCl is unavailable or the seal call errors.
    """
    try:
        import base64

        import nacl.public  # type: ignore
        import nacl.encoding  # type: ignore
    except ImportError as exc:
        raise SealFailed(f"PyNaCl unavailable: {type(exc).__name__}") from exc
    try:
        pub_bytes = base64.b64decode(server_pubkey_b64)
    except (ValueError, TypeError) as exc:
        raise BadPubkey(f"pubkey base64 decode failed: {type(exc).__name__}") from exc
    if len(pub_bytes) != 32:
        raise BadPubkey(f"pubkey must be 32 bytes, got {len(pub_bytes)}")
    try:
        pk = nacl.public.PublicKey(pub_bytes)
        sealed_box = nacl.public.SealedBox(pk)
        return sealed_box.encrypt(plaintext)
    except Exception as exc:  # PyNaCl raises a variety; map all to typed error
        raise SealFailed(f"sealedbox encrypt failed: {type(exc).__name__}") from exc


def seal_box_and_upload(
    rows: list[CanonicalRow],
    domain: str,
    server_pubkey_b64: str,
    server_url: str,
    bearer_token: str,
    maa_id: int,
    vendor_source: str,
    idempotency_key: Optional[str] = None,
    *,
    client_factory=None,
) -> UploadReceipt:
    plaintext = canonical_serialize(rows)
    canonical_sha = hashlib.sha256(plaintext).hexdigest()
    ciphertext = seal_box(plaintext, server_pubkey_b64)
    ct_sha = hashlib.sha256(ciphertext).hexdigest()

    if idempotency_key is None:
        idempotency_key = f"docker-{uuid.uuid4().hex}"

    metadata = {
        "maa_id": int(maa_id),
        "client_idempotency_key": idempotency_key,
        "vendor_source": vendor_source,
        "ciphertext_sha256": ct_sha,
        "plaintext_byte_size": len(plaintext),
        "domain": domain,
        "source": "companion-docker-csv-ingest",
    }
    url = f"{server_url.rstrip('/')}/api/v1/migration/companion/upload/"
    factory = client_factory or (lambda: httpx.Client(verify=True, timeout=60.0))
    files = {
        "ciphertext": ("companion.bin", ciphertext, "application/octet-stream"),
    }
    data = {"metadata": json.dumps(metadata)}
    try:
        with factory() as client:
            response = client.post(
                url,
                data=data,
                files=files,
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
    except httpx.HTTPError as exc:
        raise UploadRejected(0, f"transport error: {type(exc).__name__}") from exc
    # NEVER log bearer or ciphertext bytes; counts + status + domain only.
    logger.info(
        "canonical_csv.seal_box_and_upload status=%s domain=%s rows=%s",
        response.status_code, domain, len(rows),
    )
    if response.status_code >= 400:
        raise UploadRejected(response.status_code)
    body: Any = response.json()
    return UploadReceipt(
        receipt_id=int(body.get("receipt_id", 0)),
        bundle_id=body.get("bundle_id"),
        status=str(body.get("status", "")),
        canonical_sha256=canonical_sha,
    )
