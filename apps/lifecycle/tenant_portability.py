"""Full-fidelity tenant portability — export/import a tenant's whole operational
dataset between deployments (cloud ↔ on-prem edge box).

The counterpart to ``tenant_dr_snapshot`` (which is config-core only, ~13 tables):
this carries EVERY TENANT_APPS model so a running school can be moved onto a
sovereign mini-PC without losing attendance/grades/messages/analytics/payroll
history. It is also the payload format the edge↔operator sync is built on.

Design + roadmap: ``docs/plans/TIER3_TENANT_PORTABILITY_AND_EDGE_SYNC.md``.

CLONE semantics (this module): pk-preserving move into an EMPTY target. Envelope
(encryption + HMAC signature, encrypt-then-MAC, fail-closed) is reused verbatim
from :mod:`apps.lifecycle.tenant_dr_snapshot` — no new crypto.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging

from django.apps import apps as django_apps
from django.conf import settings
from django.core.serializers import deserialize, serialize
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

from apps.lifecycle.tenant_dr_snapshot import (
    decrypt_blob,
    encrypt_blob,
    sign_payload,
    verify_signature,
)

logger = logging.getLogger(__name__)

BUNDLE_FORMAT = "rmc-tenant-bundle/1"

# Canonical tenant-app set. Declared as a constant (not read from settings.TENANT_APPS)
# because that list only exists in the django-tenants settings branch — this must
# resolve in shared/RLS mode too. Mirrors config/settings.py TENANT_APPS.
TENANT_APP_LABELS: tuple[str, ...] = (
    "portal",
    "academics",
    "people",
    "schoolops",
    "finance",
    "evals",
    "reports",
    "communication",
    "feedback",
    "analytics",
    "payroll",
    "school_events",
    "student360",
    "athletics",
    "studio_os",
)


def _tenant_models() -> list:
    """Every concrete, non-proxy model in the tenant apps (deduped, stable order)."""
    seen: set[str] = set()
    models = []
    for label in TENANT_APP_LABELS:
        try:
            config = django_apps.get_app_config(label)
        except LookupError:
            continue
        for model in config.get_models():
            if model._meta.proxy or not model._meta.managed:
                continue
            key = f"{model._meta.app_label}.{model._meta.model_name}"
            if key in seen:
                continue
            seen.add(key)
            models.append(model)
    return models


def _school_field_name(model) -> str | None:
    """Return the name of a direct ``school`` FK on the model, if any."""
    for f in model._meta.get_fields():
        if getattr(f, "many_to_one", False) and f.name == "school":
            return "school"
    return None


def _scope_queryset(model, school, *, schema_mode: bool):
    """The rows to export for one model, or ``None`` if it cannot be scoped here."""
    if schema_mode:
        # Schema-per-tenant: the schema IS the tenant — every row belongs to it.
        return model._default_manager.all()
    field = _school_field_name(model)
    if field is not None:
        return model._default_manager.filter(**{field: school})
    # RLS/shared mode with no direct school FK: cannot safely scope in v1.
    return None


def _label(model) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}"


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def export_tenant_bundle(school) -> bytes:
    """Serialize the school's whole tenant dataset into an encrypted+signed bundle.

    Returns the container JSON bytes (write them to a ``.rmcbundle`` file).
    """
    schema_mode = bool(getattr(settings, "USE_DJANGO_TENANTS", False))
    tables: dict[str, list] = {}
    counts: dict[str, int] = {}
    skipped: list[str] = []
    errored: dict[str, str] = {}

    for model in _tenant_models():
        label = _label(model)
        qs = _scope_queryset(model, school, schema_mode=schema_mode)
        if qs is None:
            skipped.append(label)
            continue
        try:
            rows = json.loads(serialize("json", qs))
        except Exception as exc:  # noqa: BLE001 — record, never silently drop a table
            errored[label] = str(exc)
            logger.warning("tenant_portability: export failed for %s: %s", label, exc)
            continue
        if rows:
            tables[label] = rows
            counts[label] = len(rows)

    payload = {
        "format": BUNDLE_FORMAT,
        "tenant_slug": getattr(school, "slug", ""),
        "school_id": str(school.id),
        "created_at_iso": timezone.now().isoformat(),
        "mode": "schema" if schema_mode else "rls",
        "counts": counts,
        "skipped": skipped,   # models that couldn't be scoped (RLS, no school FK)
        "errored": errored,   # models that failed to serialize (never silent)
        "tables": tables,
    }
    raw = json.dumps(payload, cls=DjangoJSONEncoder).encode("utf-8")
    compressed = gzip.compress(raw)
    blob = encrypt_blob(compressed, school_id=str(school.id))
    sig = sign_payload(blob, school_id=str(school.id))
    container = {
        "format": BUNDLE_FORMAT,
        "school_id": str(school.id),
        "sig": sig,
        "blob_b64": base64.b64encode(blob).decode("ascii"),
    }
    return json.dumps(container).encode("utf-8")


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
def _order_labels_by_dependency(labels: list[str]) -> list[str]:
    """Topological order so a model's in-bundle FK parents load before it.

    Self-references are ignored (pk-preserving save + deferred checks handle them);
    any residual cycle is appended at the end so nothing is dropped.
    """
    present = set(labels)
    models = {}
    for label in labels:
        app_label, model_name = label.split(".", 1)
        try:
            models[label] = django_apps.get_model(app_label, model_name)
        except LookupError:
            models[label] = None

    deps: dict[str, set[str]] = {label: set() for label in labels}
    for label, model in models.items():
        if model is None:
            continue
        for f in model._meta.get_fields():
            if (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False)) and getattr(f, "concrete", False):
                rel = f.related_model
                rlabel = f"{rel._meta.app_label}.{rel._meta.model_name}"
                if rlabel in present and rlabel != label:
                    deps[label].add(rlabel)

    ordered: list[str] = []
    done: set[str] = set()
    # Kahn-style with deterministic tie-break; cycle-safe.
    remaining = list(labels)
    progressed = True
    while remaining and progressed:
        progressed = False
        for label in list(remaining):
            if deps[label] <= done:
                ordered.append(label)
                done.add(label)
                remaining.remove(label)
                progressed = True
    ordered.extend(remaining)  # residual cycles, order-preserved
    return ordered


def import_tenant_bundle(container_bytes: bytes, *, expected_school_id=None) -> dict:
    """Verify, decrypt, and load a bundle into the current deployment (pk-preserving).

    Fail-closed: the signature (and bound school id) is verified BEFORE any decrypt
    or write. Transactional: rolls back on any constraint failure. Idempotent: a
    colliding pk is an update of the same identity.
    """
    container = json.loads(container_bytes)
    school_id = str(container["school_id"])
    if expected_school_id is not None and str(expected_school_id) != school_id:
        raise ValueError("tenant_bundle_school_mismatch")

    blob = base64.b64decode(container["blob_b64"])
    if not verify_signature(blob, container["sig"], school_id=school_id):
        raise ValueError("tenant_bundle_signature_mismatch")  # fail closed

    payload = json.loads(gzip.decompress(decrypt_blob(blob, school_id=school_id)))
    tables: dict[str, list] = payload.get("tables", {}) or {}

    imported: dict[str, int] = {}
    order = _order_labels_by_dependency(list(tables.keys()))
    with transaction.atomic():
        with connection.constraint_checks_disabled():
            for label in order:
                rows = tables.get(label) or []
                n = 0
                for obj in deserialize("json", json.dumps(rows), ignorenonexistent=True):
                    obj.save()  # pk preserved
                    n += 1
                imported[label] = n
        connection.check_constraints()

    return {
        "school_id": school_id,
        "tenant_slug": payload.get("tenant_slug", ""),
        "mode": payload.get("mode", ""),
        "imported": imported,
        "total": sum(imported.values()),
        "skipped": payload.get("skipped", []),
        "errored": payload.get("errored", {}),
    }
