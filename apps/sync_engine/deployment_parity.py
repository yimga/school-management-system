"""What must be IDENTICAL on the cloud and a sovereign box -- and what must not be.

``parity.py`` (G8) proves the two sides hold the same ROWS. Nothing proved they run
the same CODE, the same SCHEMA, or the same SHIPPED ASSETS, and that gap is not
theoretical: on 2026-08-22 an operator reported two bugs that had been fixed in
``main`` on 2026-08-19 and 2026-08-20 and had reached neither deployment, because CI
had not started a job since 2026-08-15 ("The job was not started because an Actions
budget is preventing further use"). Every symptom looked like a product defect. Every
one was a delivery defect. Nothing in the system could say so.

"Make them 100% replicas" is the right instinct and the wrong target. There are three
classes, and conflating them means either chasing phantom drift forever or shipping a
real security defect:

MUST_MATCH   The commit, the applied migrations, the service-worker build. If these
             differ, the box is running software the cloud has never tested against
             the schema it is syncing into. This is the class that was invisible.

MAY_DIFFER   Network identity, region, timezone, locale, AI provider, storage
             backend, mail backend. A box in a school on a 3G uplink is SUPPOSED to
             differ from a cloud dyno. Reporting these as drift trains everyone to
             ignore the report -- which is how a MUST_MATCH finding gets lost.

MUST_DIFFER  SECRET_KEY, credentials, tokens. If these MATCH, someone copied a
             production env file onto a mini-PC that lives in a school office, and a
             stolen box is now a stolen cloud. Equality here is the finding.

The taxonomy is declared, not inferred. A setting nobody classified is reported as
UNCLASSIFIED rather than silently assumed safe: ``config/settings_registry.py`` is the
list of things we know we have, and this is the list of things we know how to compare.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any

MUST_MATCH = "MUST_MATCH"
MAY_DIFFER = "MAY_DIFFER"
MUST_DIFFER = "MUST_DIFFER"
UNCLASSIFIED = "UNCLASSIFIED"

#: Settings that are part of the product contract. A box that disagrees with the cloud
#: here is running a different product, not a differently-configured one.
PARITY_MUST_MATCH: frozenset[str] = frozenset(
    {
        "APP_VERSION",
        "RMC_RELEASE_VERSION",
        "USE_DJANGO_TENANTS",
        "LANGUAGES",
        "AUTH_USER_MODEL",
        "DEFAULT_AUTO_FIELD",
    }
)

#: Divergence here IS the design: different network, country, clock and hardware.
PARITY_MAY_DIFFER: frozenset[str] = frozenset(
    {
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "MULTI_TENANT_BASE_DOMAIN",
        "SINGLE_TENANT",
        "DEBUG",
        "TIME_ZONE",
        "LANGUAGE_CODE",
        "SECURE_SSL_REDIRECT",
        "SESSION_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
        "SECURE_HSTS_SECONDS",
        "EMAIL_BACKEND",
        "DEFAULT_FILE_STORAGE",
        "STATICFILES_STORAGE",
        "CACHES",
        "CELERY_BROKER_URL",
        "DATABASES",
        "AI_GATEWAY_PROVIDER",
        "RMC_EDGE_SYNC_ENABLED",
        "RMC_EDGE_SCHOOL_SLUG",
        "RMC_EDGE_OPERATOR_BASE",
        "CONVERSION_LOCK_STRICT",
    }
)

#: Equality is the finding. Never print the values -- only whether they collide.
PARITY_MUST_DIFFER: frozenset[str] = frozenset(
    {
        "SECRET_KEY",
        "RMC_EDGE_CREDENTIAL",
        "FIELD_ENCRYPTION_KEY",
        "RMC_EDGE_PURGE_HMAC_KEY",
    }
)


def classify(name: str) -> str:
    if name in PARITY_MUST_MATCH:
        return MUST_MATCH
    if name in PARITY_MUST_DIFFER:
        return MUST_DIFFER
    if name in PARITY_MAY_DIFFER:
        return MAY_DIFFER
    return UNCLASSIFIED


def _digest(value: Any) -> str:
    """Stable short digest. Used for MUST_DIFFER so a secret is compared, never shown."""
    return hashlib.sha256(repr(value).encode("utf-8", "replace")).hexdigest()[:16]


@dataclass
class Fingerprint:
    """Everything one deployment can say about itself without leaking anything."""

    code: dict[str, str] = field(default_factory=dict)
    schema: dict[str, Any] = field(default_factory=dict)
    assets: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "schema": self.schema,
            "assets": self.assets,
            "settings": self.settings,
        }


def local_fingerprint() -> Fingerprint:
    from django.conf import settings as dj

    from apps.siteconfig import deploy_meta

    fingerprint = Fingerprint()
    fingerprint.code = {
        "commit_sha": deploy_meta.resolve_deploy_commit_sha(),
        "app_version": str(getattr(dj, "APP_VERSION", "unknown")),
    }
    for attr, key in (
        ("resolve_build_time", "build_time"),
        ("resolve_deploy_environment", "environment"),
        ("read_service_worker_cache_version", "service_worker_cache_version"),
    ):
        resolver = getattr(deploy_meta, attr, None)
        if resolver is None:
            continue
        try:
            value = str(resolver())
        except Exception:  # noqa: BLE001 - metadata must never break the report
            continue
        if key == "service_worker_cache_version":
            fingerprint.assets[key] = value
        else:
            fingerprint.code[key] = value

    fingerprint.schema = schema_fingerprint()

    for name in sorted(PARITY_MUST_MATCH | PARITY_MAY_DIFFER):
        if hasattr(dj, name):
            fingerprint.settings[name] = _digest(getattr(dj, name))
    for name in sorted(PARITY_MUST_DIFFER):
        value = getattr(dj, name, None) or os.getenv(name, "")
        # Digest only. A parity report that prints SECRET_KEY is a worse bug than the
        # drift it was written to find.
        fingerprint.settings[name] = _digest(value) if value else ""
    return fingerprint


def schema_fingerprint() -> dict[str, Any]:
    """Applied migrations, per app, as a count plus a digest of the ordered names.

    Not the whole table: the two sides run different topologies (schema-per-tenant vs
    shared-DB + RLS), so ``django_migrations`` row ids and timestamps differ
    legitimately. What must agree is WHICH migrations have been applied.
    """
    try:
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder

        recorder = MigrationRecorder(connection)
        if not recorder.has_table():
            return {"available": False, "reason": "no django_migrations table"}
        applied = sorted(recorder.applied_migrations())
    except Exception as exc:  # noqa: BLE001 - a box mid-migration must still report
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}

    per_app: dict[str, int] = {}
    for app_label, _name in applied:
        per_app[app_label] = per_app.get(app_label, 0) + 1
    return {
        "available": True,
        "total": len(applied),
        "digest": _digest(applied),
        "per_app": per_app,
    }


@dataclass
class Finding:
    dimension: str
    key: str
    verdict: str  # DRIFT | COLLISION | EXPECTED | UNKNOWN
    detail: str

    @property
    def is_defect(self) -> bool:
        return self.verdict in {"DRIFT", "COLLISION"}


def compare(local: dict[str, Any], remote: dict[str, Any]) -> list[Finding]:
    """Diff two fingerprints under the taxonomy. Argument order is (local, remote)."""
    findings: list[Finding] = []

    for dimension in ("code", "assets"):
        local_side = local.get(dimension) or {}
        remote_side = remote.get(dimension) or {}
        for key in sorted(set(local_side) | set(remote_side)):
            left, right = local_side.get(key), remote_side.get(key)
            if left is None or right is None:
                findings.append(
                    Finding(dimension, key, "UNKNOWN", "not reported by one side")
                )
            elif key == "environment":
                # A box is not a cloud dyno and never claims to be.
                findings.append(Finding(dimension, key, "EXPECTED", f"{left} vs {right}"))
            elif left != right:
                findings.append(
                    Finding(dimension, key, "DRIFT", f"local={left} remote={right}")
                )

    local_schema = local.get("schema") or {}
    remote_schema = remote.get("schema") or {}
    if local_schema.get("available") and remote_schema.get("available"):
        if local_schema.get("digest") != remote_schema.get("digest"):
            findings.append(
                Finding(
                    "schema",
                    "applied_migrations",
                    "DRIFT",
                    f"local={local_schema.get('total')} applied, "
                    f"remote={remote_schema.get('total')} applied",
                )
            )
    else:
        findings.append(
            Finding(
                "schema",
                "applied_migrations",
                "UNKNOWN",
                local_schema.get("reason") or remote_schema.get("reason") or "not reported",
            )
        )

    local_settings = local.get("settings") or {}
    remote_settings = remote.get("settings") or {}
    for key in sorted(set(local_settings) | set(remote_settings)):
        left, right = local_settings.get(key), remote_settings.get(key)
        kind = classify(key)
        if left is None or right is None:
            findings.append(
                Finding("settings", key, "UNKNOWN", f"{kind}: not reported by one side")
            )
        elif kind == MUST_MATCH and left != right:
            findings.append(Finding("settings", key, "DRIFT", "MUST_MATCH but differs"))
        elif kind == MUST_DIFFER and left == right and left:
            findings.append(
                Finding(
                    "settings",
                    key,
                    "COLLISION",
                    "MUST_DIFFER but IDENTICAL -- the same secret is on both sides",
                )
            )
        elif kind == UNCLASSIFIED:
            findings.append(
                Finding("settings", key, "UNKNOWN", "not classified in deployment_parity")
            )
    return findings
