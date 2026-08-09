"""Vendor API pull intake — authorized REST export endpoints (stdlib HTTP only)."""

from __future__ import annotations

import io
import mimetypes
from typing import Any, Iterator

from apps.migration_cloud import defaults as mc_defaults
from apps.migration_cloud.models import IntakeMethod

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
    sha256_of_stream,
)
from .net_guard import fetch_http_capped


class APIPullIntakeAdapter(IntakeAdapter):
    """Pull JSON or CSV from an authorized vendor API URL.

    Handle shape::

        {
            "url": "https://vendor.example/api/export/students",
            "api_token": "<token>",
            "artifact_name": "students.json",
        }

    Never logs tokens. Respects HTTP error responses without retry storms.
    """

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        if not isinstance(handle, dict):
            raise IntakeError("API_PULL handle must be a dict with url and api_token")
        if not handle.get("url"):
            raise IntakeError("API_PULL requires url")
        if not handle.get("api_token"):
            raise IntakeError("API_PULL requires api_token")

    def iter_artifacts(self, handle: Any, ctx: IntakeContext) -> Iterator[ArtifactPayload]:
        url = str(handle["url"])
        token = str(handle["api_token"])
        name = str(handle.get("artifact_name") or "api_export.bin")
        try:
            max_bytes = int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))
        except Exception:  # noqa: BLE001 — safe fallback
            max_bytes = 5 * 1024 * 1024 * 1024
        # SSRF-guarded: fetch_http_capped validates the host is public BEFORE
        # building the request, so a url of http://169.254.169.254/... (or any
        # RFC-1918 / loopback host) never receives the Authorization: Bearer
        # token; every redirect hop is re-validated and the body is streamed
        # under the per-artifact byte cap.
        payload, _content_type = fetch_http_capped(
            url,
            max_bytes=max_bytes,
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/csv",
            },
        )

        if not payload:
            raise IntakeError("API_PULL returned empty body")

        digest, byte_size = sha256_of_stream(io.BytesIO(payload))
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        buffer = io.BytesIO(payload)

        def _opener() -> io.BytesIO:
            buffer.seek(0)
            return io.BytesIO(buffer.read())

        yield ArtifactPayload(
            path_within_bundle=name,
            filename=name,
            byte_size=byte_size,
            sha256=digest,
            mime_type=mime,
            content_opener=_opener,
            extra={"source": "api_pull", "url_host": _safe_host(url)},
        )


def _safe_host(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


register_adapter(IntakeMethod.API_PULL, APIPullIntakeAdapter())
