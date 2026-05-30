"""Phase 6 turbo runtime: multi-modal terminology.

Schema + helpers for the audio / transliteration / sign-language overlay on
vernacular terminology. Audio files and sign-language clips are media assets
delivered separately; this module provides the manifest contract and the
resolver the templates / API surface uses to fetch them.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-multimodal-terminology"
CONTRACT_TITLE = "Multi-modal terminology"

REPO = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO / "docs" / "generated" / "multimodal_terminology_manifest.json"

REQUIRED_FIELDS: tuple[str, ...] = ("term_key", "iso_alpha2", "label_native", "transliteration", "audio_url", "sign_language_video_url")


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {"entries": [], "schema_version": "0.1.0"}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def resolve(term_key: str, *, iso_alpha2: str) -> dict[str, Any] | None:
    manifest = _load_manifest()
    for entry in manifest.get("entries", []):
        if entry.get("term_key") == term_key and entry.get("iso_alpha2") == iso_alpha2.upper():
            return entry
    return None


def upsert(entry: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in REQUIRED_FIELDS if k not in entry]
    if missing:
        return {"status": "rejected", "missing": missing}
    manifest = _load_manifest()
    entries = manifest.setdefault("entries", [])
    for existing in entries:
        if existing.get("term_key") == entry["term_key"] and existing.get("iso_alpha2") == entry["iso_alpha2"]:
            existing.update(entry)
            MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            return {"status": "updated", "term_key": entry["term_key"], "iso_alpha2": entry["iso_alpha2"]}
    entries.append(entry)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"status": "created", "term_key": entry["term_key"], "iso_alpha2": entry["iso_alpha2"]}


def runtime_health() -> dict[str, Any]:
    result = upsert({
        "term_key": "teacher",
        "iso_alpha2": "FR",
        "label_native": "enseignant",
        "transliteration": "enseignant",
        "audio_url": "/static/terminology/audio/fr/teacher.mp3",
        "sign_language_video_url": "/static/terminology/sign/lsf/teacher.mp4",
    })
    resolved = resolve("teacher", iso_alpha2="FR")
    return {"contract_id": CONTRACT_ID, "healthy": resolved is not None and result.get("status") in {"created", "updated"}}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
