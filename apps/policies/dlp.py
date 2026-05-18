"""Field-level DLP redaction (Move 3).

Wraps a record dict or list-of-records with the PDP. For each field
defined in the entity catalog with a sensitivity tier > public, the PDP
is consulted; if denied the value is replaced according to the field's
``dlp_redaction_strategy`` (null / mask / hash / tokenize).
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Iterable

from apps.policies.pdp import allowed


def _strategy_redact(value, strategy: str) -> object:
    if value is None:
        return None
    s = (strategy or "null").lower()
    if s == "null":
        return None
    if s == "mask":
        text = str(value)
        if len(text) <= 4:
            return "***"
        return text[:2] + "***" + text[-2:]
    if s == "hash":
        return "sha256:" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
    if s == "tokenize":
        return "tok_" + secrets.token_urlsafe(8)
    return None


def redact_record(
    record: dict,
    *,
    entity: str,
    subject: dict,
    school=None,
    field_meta: dict | None = None,
    action: str = "read",
) -> dict:
    """Return a *copy* of ``record`` with disallowed fields redacted.

    Parameters
    ----------
    record
        Raw dict (e.g. from a model_to_dict or a serializer.data row).
    entity
        Logical entity name, e.g. ``"student"``.
    subject
        ``{"user_id":..., "role":...}``.
    school
        Tenant scope.
    field_meta
        Optional pre-fetched ``{field_name: {"sensitivity_tier": "...",
        "compliance_tags": [...], "dlp_redaction_strategy": "..."}}`` to avoid
        a per-record DB hit. If omitted, ``load_field_meta(entity)`` is used.
    action
        Defaults to ``"read"``; pass ``"export"`` for export pipelines.
    """

    fm = field_meta if field_meta is not None else load_field_meta(entity)
    if not fm:
        return dict(record)
    out = dict(record)
    for fname, meta in fm.items():
        if fname not in out:
            continue
        tier = meta.get("sensitivity_tier") or "internal"
        if tier == "public":
            continue
        resource = {
            "entity": entity,
            "field": fname,
            "sensitivity_tier": tier,
            "compliance_tags": meta.get("compliance_tags") or [],
            "id": out.get("id") or out.get("pk") or "",
        }
        # Field-level checks should never log; the volume would dominate.
        if allowed(subject, action, resource, school=school, log=False):
            continue
        out[fname] = _strategy_redact(out[fname], meta.get("dlp_redaction_strategy") or "null")
    return out


def redact_iterable(
    records: Iterable[dict],
    *,
    entity: str,
    subject: dict,
    school=None,
    action: str = "read",
) -> list[dict]:
    fm = load_field_meta(entity)
    return [
        redact_record(
            r, entity=entity, subject=subject, school=school, field_meta=fm, action=action
        )
        for r in records
    ]


def load_field_meta(entity: str) -> dict:
    """Return a mapping ``{field_name: {sensitivity_tier, compliance_tags, dlp_redaction_strategy}}``.

    Cheap, cached on the calling site if needed; we re-query each call to stay correct
    when the catalog changes mid-process.
    """

    try:
        from apps.metadata.models import FieldCatalogEntry

        rows = FieldCatalogEntry.objects.filter(entity__code=entity).values(
            "field_name", "sensitivity_tier", "compliance_tags", "dlp_redaction_strategy"
        )
        return {r["field_name"]: r for r in rows}
    except Exception:
        return {}
