"""v4.00.78 — LMS PKI bundle export helper.

When an operator needs to hand off their LMS connector configuration to
counsel (incident response), to a successor admin, or to a downstream
auditor, they want a single self-describing bundle: which providers are
configured, which are scaffold, what the canonical OAuth endpoints are,
what the public-key fingerprints look like (NEVER the private keys or
client secrets), and which Celery beats sweep them.

This module exports the bundle SAFELY — secrets are excluded by
construction (no env / setting reads of the *_SECRET / *_PRIVATE_KEY
pattern). The bundle is JSON-serializable and operator-facing.

Surface:
  * ``build_lms_pki_bundle()`` -> dict
  * ``bundle_fingerprint(bundle)`` -> str  — SHA-256[:16] of the canonical
    JSON form. Useful for tamper-evident hand-off receipts.

Bundle shape:
  {
    "generated_at": "...",
    "schema_version": "v4.00.78",
    "providers": [
      {
        "slug": "canvas",
        "label": "Canvas LMS",
        "maturity": "production",
        "oauth_ready": True,
        "is_scaffold": False,
        "authorize_url": "<provider-specific or empty>",
        "token_url": "<provider-specific or empty>",
        "default_scopes": [...],
      },
      ...
    ],
    "beats_in_use": ["integrations-lms-token-refresh", ...],
    "audit_tables": ["LMSDiagActionAudit", "LMSPushGradeAudit"],
    "retention_default_years": 7,
    "notes": ["..."],
  }
"""
from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger(__name__)


SCHEMA_VERSION = "v4.00.78"


def _provider_endpoints(slug: str) -> dict:
    """Return ``{authorize_url, token_url, default_scopes}`` per provider
    using the in-tree connector modules where available. Scaffold
    providers expose the same shape (per v4.00.69+ design)."""
    if slug == "canvas":
        # Canvas authorize/token URLs are operator-instance-specific
        # (per-school subdomain). Expose the spec-required path suffixes only.
        return {
            "authorize_url_suffix": "/login/oauth2/auth",
            "token_url_suffix": "/login/oauth2/token",
            "default_scopes": ["url:GET|/api/v1/courses", "url:POST|/api/v1/courses/:course_id/assignments"],
        }
    if slug == "moodle":
        return {
            "authorize_url_suffix": "/login/oauth2.php",
            "token_url_suffix": "/login/token.php",
            "default_scopes": [],
        }
    if slug in ("google_classroom", "google"):
        return {
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "default_scopes": [
                "https://www.googleapis.com/auth/classroom.courses.readonly",
                "https://www.googleapis.com/auth/classroom.coursework.students",
            ],
        }
    if slug == "schoology":
        try:
            from apps.integrations_marketplace import lms_connector_schoology as sg
            return {
                "authorize_url": sg.DEFAULT_AUTHORIZE_URL,
                "token_url": sg.DEFAULT_TOKEN_URL,
                "default_scopes": [],
            }
        except Exception:  # noqa: BLE001
            return {}
    if slug == "d2l_brightspace":
        try:
            from apps.integrations_marketplace import lms_connector_d2l as d2l
            return {
                "authorize_url": d2l.DEFAULT_AUTHORIZE_URL,
                "token_url": d2l.DEFAULT_TOKEN_URL,
                "default_scopes": list(d2l.DEFAULT_SCOPES),
            }
        except Exception:  # noqa: BLE001
            return {}
    return {}


def build_lms_pki_bundle() -> dict:
    """Build the operator-facing PKI bundle. NEVER raises."""
    try:
        from apps.integrations_marketplace import lms_supported_providers as lsp
        provider_slugs = list(lsp.lms_provider_rollup_order())
        cards = lsp.lms_provider_rollup_card()
        cards_by_slug = {c["slug"]: c for c in cards}
    except Exception as exc:  # noqa: BLE001
        logger.debug("pki bundle: lsp unavailable: %s", exc)
        provider_slugs = []
        cards_by_slug = {}

    providers = []
    for slug in provider_slugs:
        card = cards_by_slug.get(slug, {})
        endpoints = _provider_endpoints(slug)
        providers.append({
            "slug": slug,
            "label": card.get("label", slug),
            "maturity": card.get("maturity", "unknown"),
            "oauth_ready": card.get("oauth_ready", False),
            "is_scaffold": card.get("is_scaffold", False),
            **endpoints,
        })

    from django.utils import timezone as _tz
    return {
        "generated_at": _tz.now().isoformat(),
        "schema_version": SCHEMA_VERSION,
        "providers": providers,
        "beats_in_use": [
            "integrations-lms-token-refresh",
            "integrations-lms-token-rotation",
            "integrations-lms-oauth-health",
            "integrations-lms-oauth-auto-prune",
            "integrations-lms-audit-retention",
            "integrations-purge-lms-diag-action-rows",
        ],
        "audit_tables": ["LMSDiagActionAudit", "LMSPushGradeAudit"],
        "retention_default_years": 7,
        "notes": [
            "Bundle excludes secrets by construction — only public endpoint "
            "URLs + scope strings + provider maturity pills. Safe to attach "
            "to counsel hand-off PDFs.",
            "Use bundle_fingerprint() to mint a tamper-evident receipt.",
        ],
    }


def bundle_fingerprint(bundle: dict) -> str:
    """Return ``sha256(canonical-json-of-bundle)[:16]``. Stable across
    Python versions because we sort keys + use compact separators."""
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# v4.00.83 — CSV export for counsel-handoff spreadsheet ingestion.
#
# Returns a gzipped CSV. Deterministic: rows sorted by provider slug,
# columns in fixed order, gzip mtime=0 so byte-for-byte stable across
# re-runs. Caller is responsible for HTTP wiring (Content-Type +
# Content-Encoding=gzip + Content-Disposition).
import csv
import gzip
import io


_PKI_CSV_COLUMNS = (
    "slug", "label", "maturity", "oauth_ready", "is_scaffold",
    "authorize_url", "token_url", "authorize_url_suffix",
    "token_url_suffix", "default_scopes",
)


def render_pki_bundle_csv(bundle: dict) -> bytes:
    """Return the providers array of `bundle` as gzipped CSV bytes.
    Stable shape — providers sorted by slug. Empty cells for missing
    optional fields. Lists serialized as ';'-separated."""
    providers = sorted(bundle.get("providers", []), key=lambda p: p.get("slug", ""))

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    # Header
    writer.writerow(["#schema_version", bundle.get("schema_version", "")])
    writer.writerow(["#generated_at", bundle.get("generated_at", "")])
    writer.writerow([])  # blank line separator
    writer.writerow(_PKI_CSV_COLUMNS)
    for prov in providers:
        scopes = prov.get("default_scopes", [])
        if isinstance(scopes, (list, tuple)):
            scopes_cell = ";".join(str(s) for s in scopes)
        else:
            scopes_cell = str(scopes or "")
        writer.writerow([
            prov.get("slug", ""),
            prov.get("label", ""),
            prov.get("maturity", ""),
            "true" if prov.get("oauth_ready") else "false",
            "true" if prov.get("is_scaffold") else "false",
            prov.get("authorize_url", ""),
            prov.get("token_url", ""),
            prov.get("authorize_url_suffix", ""),
            prov.get("token_url_suffix", ""),
            scopes_cell,
        ])

    csv_bytes = buf.getvalue().encode("utf-8")
    out = io.BytesIO()
    # mtime=0 -> deterministic across re-runs
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(csv_bytes)
    return out.getvalue()


def decode_pki_bundle_csv(blob: bytes) -> str:
    """Inverse of render_pki_bundle_csv — returns the CSV text. Helper
    for tests + operators who downloaded the file."""
    return gzip.decompress(blob).decode("utf-8")


# v4.00.84 — Import + validate counterparts to build/export.

class PKIBundleImportError(Exception):
    """Raised when a bundle import cannot proceed."""


def import_pki_bundle(blob: bytes | str) -> dict:
    """Reverse of build_lms_pki_bundle()+json.dumps. Accepts either
    bytes (utf-8 JSON) or a str.

    Raises PKIBundleImportError on:
      - Non-JSON input
      - JSON that is not a dict
      - Missing required top-level keys (providers, schema_version)
    """
    if isinstance(blob, bytes):
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PKIBundleImportError(f"bad_encoding: {exc}") from exc
    elif isinstance(blob, str):
        text = blob
    else:
        raise PKIBundleImportError("expected_bytes_or_str")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PKIBundleImportError(f"bad_json: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise PKIBundleImportError("not_a_dict")
    for required in ("providers", "schema_version"):
        if required not in parsed:
            raise PKIBundleImportError(f"missing_required_key:{required}")
    return parsed


def validate_pki_bundle(bundle: dict, *, expected_fingerprint: str | None = None) -> dict:
    """Structural + (optional) tamper validation. Returns
    {"ok": bool, "issues": [str, ...], "fingerprint": str}.
    NEVER raises.

    Issues collected:
      - missing_required_key:<name>
      - bad_type:<name>
      - provider_missing_slug
      - provider_invalid_label
      - schema_version_drift (if expected_fingerprint passed and current
        bundle fingerprint doesn't match)
      - fingerprint_mismatch:expected=<e>,actual=<a> (if expected_fingerprint
        given and doesn't match)
    """
    issues: list[str] = []
    fp = ""
    try:
        if not isinstance(bundle, dict):
            return {"ok": False, "issues": ["not_a_dict"], "fingerprint": ""}
        for required in ("providers", "schema_version", "beats_in_use"):
            if required not in bundle:
                issues.append(f"missing_required_key:{required}")
        if "providers" in bundle and not isinstance(bundle["providers"], list):
            issues.append("bad_type:providers")
        for prov in bundle.get("providers", []):
            if not isinstance(prov, dict):
                issues.append("bad_type:provider_row")
                continue
            if not prov.get("slug"):
                issues.append("provider_missing_slug")
            label = prov.get("label", "")
            if not isinstance(label, str) or not label.strip():
                issues.append("provider_invalid_label")
        try:
            fp = bundle_fingerprint(bundle)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"fingerprint_error:{type(exc).__name__}")
        if expected_fingerprint is not None and fp and expected_fingerprint != fp:
            issues.append(f"fingerprint_mismatch:expected={expected_fingerprint},actual={fp}")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"validation_error:{type(exc).__name__}")
    return {"ok": len(issues) == 0, "issues": issues, "fingerprint": fp}


def export_pki_bundle_json(bundle: dict) -> bytes:
    """Canonical JSON serialization for round-trip safety. Same shape as
    bundle_fingerprint() uses internally — sort_keys + compact separators."""
    return json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode("utf-8")
