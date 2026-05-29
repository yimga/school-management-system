"""
Marketing i18n quality gates: seed completeness vs production native-review.

Seed gate (dev/CI default): French marketing strings seeded + review packet +
``var/i18n-review-status.json`` tracks ``needs-native-review``.

Production gate (``--production``): marketing locales must be ``production-ready``.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings

from apps.schools.marketing_content_seed import (
    FRENCH_MARKETING_MSGID_ANCHORS,
    _parse_po_msgstr_by_msgid,
    validate_french_marketing_translations,
)

REVIEW_STATUS_REL = "var/i18n-review-status.json"
FR_REVIEW_PACKET_REL = "docs/i18n/translation_requests/fr.md"

# Locales that gate public marketing deploy until native-reviewed.
MARKETING_PRODUCTION_LOCALES: tuple[str, ...] = (
    "fr",
    "es",
    "pt-br",
)


def _repo_root() -> Path:
    return Path(settings.BASE_DIR)


def load_i18n_review_status() -> dict:
    path = _repo_root() / REVIEW_STATUS_REL
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def validate_marketing_i18n_seed_gate() -> list[str]:
    """
    Dev/seed gate: French anchors populated, review ledger present, fr packet exists.
    """
    errors: list[str] = []
    errors.extend(validate_french_marketing_translations())

    status_path = _repo_root() / REVIEW_STATUS_REL
    if not status_path.is_file():
        errors.append(f"missing i18n review ledger: {REVIEW_STATUS_REL}")
        return errors

    locales = (load_i18n_review_status().get("locales") or {})
    fr = locales.get("fr") or {}
    review_status = fr.get("review_status", "")
    if review_status not in ("needs-native-review", "production-ready"):
        errors.append(
            f"fr review_status must be needs-native-review or production-ready, got {review_status!r}"
        )

    packet = _repo_root() / FR_REVIEW_PACKET_REL
    if not packet.is_file():
        errors.append(f"missing French native-review packet: {FR_REVIEW_PACKET_REL}")
    return errors


def validate_marketing_i18n_production_gate() -> list[str]:
    """Production deploy gate: marketing locales must be native-reviewed."""
    errors: list[str] = []
    locales = (load_i18n_review_status().get("locales") or {})
    for code in MARKETING_PRODUCTION_LOCALES:
        entry = locales.get(code) or {}
        status = entry.get("review_status", "unreviewed")
        if status != "production-ready":
            reviewer = entry.get("reviewer") or "—"
            errors.append(
                f"marketing locale {code!r} not production-ready "
                f"(status={status!r}, reviewer={reviewer}). "
                f"Run: python manage.py i18n_review_status --mark-reviewed {code} "
                f'--reviewer "<native speaker>"'
            )
    return errors


def count_french_marketing_translations_in_po() -> int:
    """Count non-empty msgstr among anchor marketing msgids in fr.po."""
    fr_po = _repo_root() / "locale" / "fr" / "LC_MESSAGES" / "django.po"
    if not fr_po.is_file():
        return 0
    try:
        by_msgid = _parse_po_msgstr_by_msgid(fr_po.read_text(encoding="utf-8"))
    except OSError:
        return 0
    return sum(
        1
        for msgid in FRENCH_MARKETING_MSGID_ANCHORS
        if (by_msgid.get(msgid) or "").strip()
    )


def sync_french_review_status_in_ledger(*, seed_batch: str = "1568") -> bool:
    """
    Refresh fr.translated_target_strings + notes in var/i18n-review-status.json.
    Returns True when file was updated.
    """
    path = _repo_root() / REVIEW_STATUS_REL
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    locales = payload.setdefault("locales", {})
    fr = locales.setdefault("fr", {})
    fr["review_status"] = fr.get("review_status") or "needs-native-review"
    fr["kind"] = fr.get("kind") or "ai-draft"
    fr["translated_target_strings"] = count_french_marketing_translations_in_po()
    fr["notes"] = (
        f"AI-drafted via seed_marketing_site (batch {seed_batch}). "
        "Native-speaker review packet: docs/i18n/translation_requests/fr.md. "
        "Flip to production-ready: "
        "python manage.py i18n_review_status --mark-reviewed fr --reviewer \"<name>\"."
    )
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return True
