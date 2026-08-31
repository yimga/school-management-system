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
from collections import deque
from functools import lru_cache

from django.apps import apps as django_apps
from django.conf import settings
from django.core.serializers import deserialize, serialize
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

# ONE implementation of "enter this school's tenant schema", deliberately not a
# second one. It lives in staff_portability because that is where it was first
# needed; the odd home is worth less than a duplicate that can drift.
from apps.lifecycle.staff_portability import school_schema
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


def _rel_model(f):
    """The resolved related-model CLASS for a relational field, or ``None``.

    ``Field.related_model`` can still be a lazy STRING (e.g. ``"portal.KBArticle"``)
    for some string-declared FKs even after app loading — accessing ``._meta`` on
    it then raises ``AttributeError: 'str' object has no attribute '_meta'``.
    Normalize to the class (or ``None`` if it can't be resolved) so callers never
    touch a bare string.
    """
    rel = getattr(f, "related_model", None)
    if isinstance(rel, str):
        try:
            return django_apps.get_model(rel)
        except (LookupError, ValueError):
            return None
    return rel


def _direct_school_field(model) -> str | None:
    """Name of a direct FK or O2O to ``schools.School`` on this model, if any.

    Both ``ForeignKey`` and ``OneToOneField`` count. An O2O sets
    ``many_to_one=False`` / ``one_to_one=True``, so the pre-2026-08 check on
    ``many_to_one`` alone silently skipped one-to-one school links
    (``analytics.RiskThresholds``, ``finance.TenantPaymentPolicy``).
    """
    try:
        school_model = django_apps.get_model("schools", "School")
    except LookupError:
        school_model = None
    for f in model._meta.get_fields():
        if (
            (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False))
            and getattr(f, "concrete", False)
            and f.name == "school"
            and (school_model is None or _rel_model(f) is school_model)
        ):
            return "school"
    return None


@lru_cache(maxsize=None)
def _school_lookup_path(model_label: str) -> str | None:
    """The ORM lookup that scopes a tenant model to its owning School in RLS mode.

    ``"school"`` for a direct link, a walked path like ``"invoice__school"`` /
    ``"employee__department__school"`` for a parent-reachable model, or ``None``
    when no path of concrete FK/O2O edges (staying inside the tenant apps)
    reaches a field named ``school`` that points at ``schools.School``.

    Breadth-first over concrete many-to-one / one-to-one edges only. It
    terminates ONLY at a field literally named ``school`` (so a "foreign" link
    such as ``source_school`` / ``target_school`` is never treated as the owner)
    and never leaves the tenant apps (so a ``created_by`` → User edge can't scope
    a row by another tenant's membership). Depth-capped. The result is always
    filtered by the one concrete ``school`` instance, so the pin is to a single
    tenant regardless of which path was chosen.

    Known v1 limitation: a model with two+ distinct paths to a school field
    (e.g. a cross-school transfer record) is scoped by whichever path the BFS
    reaches first; genuinely dual-owned rows want an explicit override.
    """
    app_label, model_name = model_label.split(".", 1)
    try:
        start = django_apps.get_model(app_label, model_name)
        school_model = django_apps.get_model("schools", "School")
    except LookupError:
        return None

    seen: set = set()
    queue: deque = deque([(start, ())])
    while queue:
        model, prefix = queue.popleft()
        if model in seen or len(prefix) > 6:
            continue
        seen.add(model)
        direct = _direct_school_field(model)
        if direct is not None:
            return "__".join(prefix + (direct,))
        for f in model._meta.get_fields():
            if not (
                (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False))
                and getattr(f, "concrete", False)
            ):
                continue
            rel = _rel_model(f)
            if rel is None or rel is model or rel is school_model:
                continue  # unresolved / self / bare foreign-School FK — reach the owner via another edge
            if rel._meta.app_label not in TENANT_APP_LABELS:
                continue  # never scope via a shared/User edge (no cross-tenant reach)
            queue.append((rel, prefix + (f.name,)))
    return None


def _scope_queryset(model, school, *, schema_mode: bool):
    """The rows to export for one model, or ``None`` if it cannot be scoped here."""
    if schema_mode:
        # Schema-per-tenant: the schema IS the tenant — every row belongs to it.
        # That premise is only true INSIDE the tenant schema. The caller is
        # responsible for entering it (see `school_schema`); run this on the default
        # connection and it is an unfiltered read of `public`, which holds a legacy
        # copy plus other tenants' rows. Measured 2026-08-31: that shipped one
        # school's teacher inside another school's bundle.
        return model._default_manager.all()
    path = _school_lookup_path(_label(model))
    if path is not None:
        # RLS/shared mode: direct or parent-reachable ``school`` link.
        return model._default_manager.filter(**{path: school}).distinct()
    # No path to School: genuinely global/shared, or a per-tenant table that
    # carries no school linkage at all (those need a school_id column added).
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

    # The schema the rows are READ from. In schema mode `_scope_queryset` drops the
    # school filter because the schema is the scope -- so entering it is not an
    # optimisation, it is the only thing making the export tenant-safe.
    # Provenance: which schema the rows came from. Read off the tenant client rather
    # than the context manager, which yields nothing.
    _client = getattr(school, "tenant_client", None)
    source_schema = str(getattr(_client, "schema_name", "") or "")
    with school_schema(school):
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
        # Which schema the rows actually came from. Absent in bundles written before
        # 2026-08-31, which is exactly the set that may carry `public`.
        "source_schema": source_schema,
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
    # Land the rows in the school's OWN schema, for the same reason the export reads
    # from it: on the default connection these writes go to `public`, where they are
    # invisible to the tenant UI and mixed in with other tenants' legacy rows. A box
    # has one schema, so this is a no-op there.
    from apps.schools.models import School

    target = School.objects.filter(pk=school_id).first()
    with school_schema(target):
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
