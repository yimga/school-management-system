"""FastAPI entry for the Docker companion sibling.

Endpoints:
  * POST /handshake/login        — RMC platform login proxy (forwards to
                                   apps/migration_cloud RMC server).
  * GET  /handshake/maa-text     — fetch MAA text for the operator to read.
  * POST /handshake/maa-sign     — sign the MAA via RMC server.
  * POST /ingest/csv             — multipart canonical-CSV ingest:
                                   parse → match domain → seal → upload.

Auth: the operator's RMC bearer token MUST be sent in the
``Authorization: Bearer <token>`` header on every endpoint here other
than /handshake/login. The Docker sibling does NOT store tokens; each
request stands alone.

Streams uploaded CSV to a SpooledTemporaryFile — NEVER writes to disk path.
"""
from __future__ import annotations

import logging
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

from . import __version__
from . import canonical_csv as csv_mod
from . import rmc_handshake

logger = logging.getLogger(__name__)

app = FastAPI(
    title=f"RunMyCampus Companion (Docker) - v{__version__}",
    description=(
        "Handshake with the RunMyCampus platform and ingest canonical "
        "CSV files the operator manually exported from their SIS. "
        "This service does NOT log into PowerSchool / Blackbaud / "
        "Veracross / Alma / FACTS / Skyward."
    ),
    version=__version__,
)


def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization must be 'Bearer <token>'")
    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="empty bearer token")
    return token


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/handshake/login")
def login_endpoint(server_url: str = Form(...), email: str = Form(...), password: str = Form(...)) -> dict[str, str]:
    """Login proxy. We deliberately return the token to the operator's
    own browser session; the Docker sibling does not persist it."""
    session = rmc_handshake.RMCSession(server_url)
    try:
        token = session.login(email, password)
    except rmc_handshake.Unauthorized as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except rmc_handshake.TransportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except rmc_handshake.HandshakeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        # Best-effort overwrite of password var (Python strings are
        # immutable, GC handles real destruction; this drops the ref).
        password = "0" * len(password)
        del password
    # Clear the bearer from session right away — caller has it.
    cleared = token
    session.clear_token()
    return {"token": cleared}


@app.get("/handshake/maa-text")
def maa_text_endpoint(
    server_url: str,
    tenant_slug: str,
    vendor: str,
    version: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, object]:
    token = _extract_bearer(authorization)
    session = rmc_handshake.RMCSession(server_url)
    session._token = token  # noqa: SLF001 — explicit, not stored elsewhere
    try:
        text = session.fetch_maa_text(tenant_slug, vendor, version)
    except rmc_handshake.Unauthorized as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except rmc_handshake.HandshakeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.clear_token()
    return {
        "vendor": text.vendor,
        "version": text.version,
        "text": text.text,
        "is_draft": text.is_draft,
        "active_version": text.active_version,
    }


@app.post("/handshake/maa-sign")
def maa_sign_endpoint(
    server_url: str = Form(...),
    tenant_slug: str = Form(...),
    vendor: str = Form(...),
    holder: str = Form(...),
    role: str = Form(...),
    agreement_version: str = Form(...),
    body: str = Form(...),
    authorization: Optional[str] = Header(default=None),
) -> dict[str, object]:
    token = _extract_bearer(authorization)
    session = rmc_handshake.RMCSession(server_url)
    session._token = token  # noqa: SLF001
    try:
        receipt = session.sign_and_submit_maa(
            tenant_slug, vendor, holder, role, agreement_version, body,
        )
    except rmc_handshake.MaaSignRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except rmc_handshake.HandshakeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.clear_token()
    return {
        "maa_id": receipt.maa_id,
        "signed_at": receipt.signed_at,
        "agreement_version": receipt.agreement_version,
    }


@app.post("/ingest/csv")
async def ingest_csv_endpoint(
    server_url: str = Form(...),
    tenant_slug: str = Form(...),
    vendor_source: str = Form(...),
    domain_hint: Optional[str] = Form(default=None),
    maa_id: int = Form(...),
    pubkey_b64: str = Form(...),
    idempotency_key: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
) -> dict[str, object]:
    """Accept multipart CSV upload, canonicalize, seal-box, upload."""
    token = _extract_bearer(authorization)

    # Stream the upload into memory (SpooledTemporaryFile) — never to disk.
    spool = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024, mode="w+b")
    try:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            spool.write(chunk)
        spool.seek(0)
        blob = spool.read()
    finally:
        spool.close()

    try:
        headers, raw_rows = csv_mod.parse_csv_bytes(blob)
    except csv_mod.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"csv parse failed: {exc}") from exc

    domain = csv_mod.match_canonical_domain(headers) or domain_hint
    if not domain:
        raise HTTPException(
            status_code=400,
            detail="csv headers do not match any canonical domain; pass domain_hint or rename columns",
        )

    canonical_rows = [csv_mod.canonicalize_row(r, domain) for r in raw_rows]
    try:
        receipt = csv_mod.seal_box_and_upload(
            rows=canonical_rows,
            domain=domain,
            server_pubkey_b64=pubkey_b64,
            server_url=server_url,
            bearer_token=token,
            maa_id=maa_id,
            vendor_source=vendor_source,
            idempotency_key=idempotency_key,
        )
    except csv_mod.BadPubkey as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except csv_mod.SealFailed as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except csv_mod.UploadRejected as exc:
        raise HTTPException(status_code=exc.status or 502, detail=str(exc)) from exc

    # Log counts + receipt_id only — NEVER cell values.
    logger.info(
        "ingest_csv: tenant_slug=%s domain=%s rows=%s receipt_id=%s",
        tenant_slug, domain, len(canonical_rows), receipt.receipt_id,
    )
    return {
        "receipt_id": receipt.receipt_id,
        "bundle_id": receipt.bundle_id,
        "status": receipt.status,
        "canonical_sha256": receipt.canonical_sha256,
        "matched_domain": domain,
        "row_count": len(canonical_rows),
        "tenant_slug": tenant_slug,
    }
