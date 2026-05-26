"""CustomerSuccess helpcenter ingestion shim for the Unified Wizard Framework.

Lands wizard answers for the ``ai_helpcenter_knowledge_injection`` wizard's
source-registration step into a per-tenant ledger on ``BillingAccount.metadata``
(re-using an existing JSON column, no migration). Future incremental work can
promote this into a first-class ``HelpcenterSource`` model.

Wizard writer calls
``_try_domain_integration("apps.customersuccess.services", "register_helpcenter_source", ...)``
so we shim that signature here. Keeps the existing ``apps/customersuccess/services.py``
focused on its tenant-health / auto-ticket responsibilities.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["register_helpcenter_source"]


_LEDGER_KEY = "helpcenter_sources"
_MAX_LEDGER_ENTRIES = 200


def register_helpcenter_source(
    *,
    school: Any,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Append a helpcenter source registration into the tenant ledger.

    Returns ``True`` on state change, ``False`` on no-op (missing school,
    empty payload, duplicate URL/filename).

    Storage shape on ``school.settings["customersuccess"]["helpcenter_sources"]``::

        [
          {"file_name": "policy.pdf", "file_size": 102400, "registered_at_iso": "..."},
          {"value": "https://help.example.com/article/1", "registered_at_iso": "..."},
          ...
        ]

    Capped at ``_MAX_LEDGER_ENTRIES`` (oldest evicted) so a buggy wizard re-run
    doesn't bloat the JSONField unboundedly.
    """
    if school is None or not payload:
        return False
    if getattr(school, "pk", None) is None:
        return False

    entry = _coerce_entry(payload)
    if entry is None:
        return False

    from datetime import datetime, timezone
    entry["registered_at_iso"] = datetime.now(tz=timezone.utc).isoformat()

    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}
    cs_bucket = settings.get("customersuccess") or {}
    if not isinstance(cs_bucket, dict):
        cs_bucket = {}
    ledger = list(cs_bucket.get(_LEDGER_KEY) or [])

    if _is_duplicate(ledger, entry):
        return False

    ledger.append(entry)
    if len(ledger) > _MAX_LEDGER_ENTRIES:
        ledger = ledger[-_MAX_LEDGER_ENTRIES:]
    cs_bucket[_LEDGER_KEY] = ledger
    settings["customersuccess"] = cs_bucket

    try:
        school.settings = settings
        school.save(update_fields=["settings"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_helpcenter_source: save failed: %s", exc)
        return False

    # v3.94.0: also write to first-class HelpcenterSource model. Best-effort —
    # if migration hasn't been applied yet (legacy environment), fall through
    # cleanly without breaking the ledger write that already succeeded above.
    _persist_first_class(school, entry)
    return True


def _persist_first_class(school, entry: dict) -> None:
    """Mirror the ledger entry into ``HelpcenterSource`` (v3.94.0 first-class promotion)."""
    try:
        from apps.customersuccess.models import HelpcenterSource
    except ImportError:
        return
    try:
        if entry.get("url") or (entry.get("value") and entry["value"].startswith(("http://", "https://"))):
            url = entry.get("url") or entry.get("value")
            # tenant-isolation-allow: helpcenter-source-create-explicit-school-fk-wizard-writer
            HelpcenterSource.objects.update_or_create(
                school=school,
                kind=HelpcenterSource.Kind.URL,
                url=url,
                defaults={},
            )
        elif entry.get("file_name"):
            # tenant-isolation-allow: helpcenter-source-create-explicit-school-fk-wizard-writer
            HelpcenterSource.objects.update_or_create(
                school=school,
                kind=HelpcenterSource.Kind.FILE,
                file_name=entry["file_name"],
                defaults={"file_size": entry.get("file_size")},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_helpcenter_source first-class write failed: %s", exc)


def _coerce_entry(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize wizard payload (file-upload or URL form) to a ledger entry."""
    value = payload.get("value")
    # File-shape payload (already sanitized by wizard_state_resolver)
    if isinstance(value, dict) and ("file_name" in value or "file_size" in value):
        return {
            "file_name": value.get("file_name"),
            "file_size": value.get("file_size"),
        }
    # Raw file-like object (writer called directly, pre-sanitization)
    if hasattr(value, "name") and hasattr(value, "size") and not isinstance(value, str):
        return {
            "file_name": getattr(value, "name", None),
            "file_size": getattr(value, "size", None),
        }
    if isinstance(value, str) and value.strip():
        return {"value": value.strip()}
    return None


def _is_duplicate(ledger: list[dict[str, Any]], entry: dict[str, Any]) -> bool:
    """Treat two entries with the same value/file_name as duplicates."""
    for existing in ledger:
        if entry.get("value") and existing.get("value") == entry["value"]:
            return True
        if entry.get("file_name") and existing.get("file_name") == entry["file_name"]:
            return True
    return False
