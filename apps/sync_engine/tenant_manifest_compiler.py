"""
Tenant manifest compiler — compiles a deterministic offline-sync manifest for
a single tenant.

The manifest exposes only what the offline / edge PWA needs to operate: route
allowlist, data policies, PWA cache hints, schema version, signature posture.
Secrets, credentials, raw PII, and cross-tenant identifiers are excluded.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class TenantManifestError(RuntimeError):
    pass


_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "signature_text",
        "ssn",
        "dob",
        "email",
    }
)


def _scrub(payload: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _SENSITIVE_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = _scrub(value)
        elif isinstance(value, list):
            clean[key] = [_scrub(item) if isinstance(item, dict) else item for item in value]
        else:
            clean[key] = value
    return clean


@dataclass
class TenantManifest:
    tenant_id_hash: str
    schema_version: int = SCHEMA_VERSION
    routes_allowlist: list[str] = field(default_factory=list)
    data_policies: dict[str, Any] = field(default_factory=dict)
    pwa_cache_hints: dict[str, Any] = field(default_factory=dict)
    locale_default: str = "en"
    feature_flags: dict[str, bool] = field(default_factory=dict)
    checksum: str = ""
    signature_posture: str = "unsigned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id_hash": self.tenant_id_hash,
            "schema_version": self.schema_version,
            "routes_allowlist": self.routes_allowlist,
            "data_policies": self.data_policies,
            "pwa_cache_hints": self.pwa_cache_hints,
            "locale_default": self.locale_default,
            "feature_flags": self.feature_flags,
            "checksum": self.checksum,
            "signature_posture": self.signature_posture,
        }


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compile_manifest(
    *,
    tenant_id: str,
    routes_allowlist: list[str] | None = None,
    data_policies: dict[str, Any] | None = None,
    pwa_cache_hints: dict[str, Any] | None = None,
    locale_default: str = "en",
    feature_flags: dict[str, bool] | None = None,
    signature_posture: str = "unsigned",
) -> TenantManifest:
    if not tenant_id:
        raise TenantManifestError("tenant_id required")
    tenant_hash = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:12]
    routes = list(routes_allowlist or [])
    if any(not isinstance(r, str) or not r.startswith("/") for r in routes):
        raise TenantManifestError("routes_allowlist entries must be absolute paths")
    policies = _scrub(dict(data_policies or {}))
    cache = _scrub(dict(pwa_cache_hints or {}))
    flags = {str(k): bool(v) for k, v in (feature_flags or {}).items()}
    if signature_posture not in {"unsigned", "hmac-sha256", "ed25519"}:
        raise TenantManifestError(f"unsupported signature_posture {signature_posture!r}")

    body = {
        "tenant_id_hash": tenant_hash,
        "schema_version": SCHEMA_VERSION,
        "routes_allowlist": sorted(routes),
        "data_policies": policies,
        "pwa_cache_hints": cache,
        "locale_default": locale_default,
        "feature_flags": flags,
    }
    checksum = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
    manifest = TenantManifest(
        tenant_id_hash=tenant_hash,
        routes_allowlist=sorted(routes),
        data_policies=policies,
        pwa_cache_hints=cache,
        locale_default=locale_default,
        feature_flags=flags,
        checksum=checksum,
        signature_posture=signature_posture,
    )
    logger.info(
        "tenant_manifest_compiler compiled tenant=%s routes=%d checksum=%s",
        tenant_hash,
        len(manifest.routes_allowlist),
        checksum[:12],
        extra={"scope": "tenant_manifest_compiler.compile"},
    )
    return manifest


__all__ = [
    "SCHEMA_VERSION",
    "TenantManifest",
    "TenantManifestError",
    "compile_manifest",
]
