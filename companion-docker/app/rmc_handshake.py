"""RMC platform handshake (v3.37.0 Agent 4 — Docker sibling).

TARGET: RunMyCampus's OWN ``/api/v1/...`` endpoints. This module
NEVER programmatically logs into any third-party SIS. Vendor data
extraction lives in ``companion-extension/`` (the browser extension
where the operator's own authenticated tab is the security boundary).
The Docker sibling's only login is to the RMC platform itself.

Mirrors the Tauri sibling's `rmc_handshake.rs` so both siblings keep
identical operator UX.
"""
from __future__ import annotations

import dataclasses
import hmac
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RMC_LOGIN_PATH = "/api/v1/auth/login/"
RMC_MAA_TEXT_PATH = "/api/v1/migration/maa/text/"
RMC_MAA_SIGN_PATH = "/api/v1/migration/maa/sign/"
RMC_RECEIPT_PATH_PREFIX = "/api/v1/migration/receipts/"

DEFAULT_TIMEOUT_SECS = 30.0


class HandshakeError(Exception):
    """Typed handshake error. Subclassed below for known cases."""


class BadServerUrl(HandshakeError):
    pass


class TransportError(HandshakeError):
    pass


class Unauthorized(HandshakeError):
    """HTTP 401 from RMC platform login."""


class Forbidden(HandshakeError):
    pass


class NotFound(HandshakeError):
    pass


class BadResponse(HandshakeError):
    pass


class MaaSignRejected(HandshakeError):
    pass


@dataclasses.dataclass
class MaaText:
    vendor: str
    version: str
    text: str
    is_draft: bool
    active_version: str


@dataclasses.dataclass
class MAAReceipt:
    maa_id: int
    signed_at: str
    agreement_version: str


@dataclasses.dataclass
class Receipt:
    receipt_id: int
    bundle_id: Optional[int]
    status: str


def _join_url(base: str, path: str) -> str:
    if not (base.startswith("http://") or base.startswith("https://")):
        raise BadServerUrl("server URL must include http:// or https://")
    return f"{base.rstrip('/')}{path}"


def _classify_status(status: int) -> HandshakeError:
    if status == 401:
        return Unauthorized(f"authentication failed status={status}")
    if status == 403:
        return Forbidden(f"forbidden status={status}")
    if status == 404:
        return NotFound(f"not found status={status}")
    return HandshakeError(f"unexpected status={status}")


def constant_time_text_eq(a: str, b: str) -> bool:
    """Constant-time equality for MAA signature_text echo + tokens.

    Python has no native zeroize; we use ``hmac.compare_digest`` which
    is the stdlib's constant-time primitive.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class RMCSession:
    """Holds the bearer token in memory only. The token is never written
    to disk, never logged, never echoed to stdout.
    """

    def __init__(
        self,
        server_url: str,
        *,
        client_factory=None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        # Caller may inject a httpx MockTransport for tests.
        self._client_factory = client_factory or (
            lambda: httpx.Client(verify=True, timeout=DEFAULT_TIMEOUT_SECS)
        )
        self._token: Optional[str] = None

    @property
    def token(self) -> Optional[str]:
        return self._token

    def clear_token(self) -> None:
        # Best-effort overwrite; Python strings are immutable so the
        # GC handles real destruction. Drop the reference.
        if self._token is not None:
            self._token = "0" * len(self._token)
            self._token = None

    def _auth_header(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    def login(self, email: str, password: str) -> str:
        """POST /api/v1/auth/login/ — returns bearer token."""
        url = _join_url(self.server_url, RMC_LOGIN_PATH)
        try:
            with self._client_factory() as client:
                response = client.post(url, json={"email": email, "password": password})
        except httpx.HTTPError as exc:
            raise TransportError(f"transport error: {type(exc).__name__}") from exc
        # Best-effort overwrite the password var locally. (Caller should
        # del password after this returns.)
        password = "0" * len(password)
        del password
        status = response.status_code
        logger.info("rmc_handshake.login status=%s", status)
        if status >= 400:
            raise _classify_status(status)
        try:
            body = response.json()
        except ValueError as exc:
            raise BadResponse("login response not JSON") from exc
        token = body.get("token") or body.get("key") or body.get("access")
        if not token or not isinstance(token, str):
            raise BadResponse("login response missing token/key/access")
        self._token = token
        return token

    def fetch_maa_text(
        self,
        tenant_slug: str,
        vendor: str,
        version: Optional[str] = None,
    ) -> MaaText:
        url = _join_url(self.server_url, RMC_MAA_TEXT_PATH)
        params = {"vendor": vendor, "tenant": tenant_slug}
        if version:
            params["version"] = version
        try:
            with self._client_factory() as client:
                response = client.get(url, params=params, headers=self._auth_header())
        except httpx.HTTPError as exc:
            raise TransportError(f"transport error: {type(exc).__name__}") from exc
        status = response.status_code
        logger.info(
            "rmc_handshake.fetch_maa_text status=%s tenant_slug=%s vendor=%s",
            status, tenant_slug, vendor,
        )
        if status >= 400:
            raise _classify_status(status)
        body = response.json()
        return MaaText(
            vendor=body.get("vendor", vendor),
            version=body.get("version", ""),
            text=body.get("text", ""),
            is_draft=bool(body.get("is_draft", False)),
            active_version=body.get("active_version", ""),
        )

    def sign_and_submit_maa(
        self,
        tenant_slug: str,
        vendor: str,
        holder: str,
        role: str,
        agreement_version: str,
        body_text: str,
    ) -> MAAReceipt:
        url = _join_url(self.server_url, RMC_MAA_SIGN_PATH)
        payload = {
            "vendor_source": vendor,
            "vendor_account_holder_name": holder,
            "signed_by_role": role,
            "agreement_version": agreement_version,
            # The server constant-time-compares this against its own
            # render. We use ``hmac.compare_digest`` on echoes locally
            # in tests, and trust the server's own constant-time check
            # at runtime.
            "submitted_signature_text": body_text,
        }
        try:
            with self._client_factory() as client:
                response = client.post(
                    url,
                    json=payload,
                    headers={**self._auth_header(), "X-Tenant": tenant_slug},
                )
        except httpx.HTTPError as exc:
            raise TransportError(f"transport error: {type(exc).__name__}") from exc
        status = response.status_code
        # NEVER log body_text — only status + IDs.
        logger.info(
            "rmc_handshake.sign_and_submit_maa status=%s tenant_slug=%s vendor=%s",
            status, tenant_slug, vendor,
        )
        if status >= 400:
            if status == 400:
                raise MaaSignRejected(f"MAA sign rejected status={status}")
            raise _classify_status(status)
        parsed = response.json()
        return MAAReceipt(
            maa_id=int(parsed["maa_id"]),
            signed_at=str(parsed.get("signed_at", "")),
            agreement_version=str(parsed.get("agreement_version", "")),
        )

    def fetch_receipt(self, receipt_id: int) -> Receipt:
        path = f"{RMC_RECEIPT_PATH_PREFIX}{receipt_id}/"
        url = _join_url(self.server_url, path)
        try:
            with self._client_factory() as client:
                response = client.get(url, headers=self._auth_header())
        except httpx.HTTPError as exc:
            raise TransportError(f"transport error: {type(exc).__name__}") from exc
        status = response.status_code
        logger.info("rmc_handshake.fetch_receipt status=%s receipt_id=%s", status, receipt_id)
        if status >= 400:
            raise _classify_status(status)
        body = response.json()
        return Receipt(
            receipt_id=int(body.get("receipt_id", receipt_id)),
            bundle_id=body.get("bundle_id"),
            status=str(body.get("status", "")),
        )
