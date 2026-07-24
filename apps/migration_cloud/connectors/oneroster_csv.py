"""OneRoster CSV connector — a real adapter over the OneRoster v1.2 file path.

Registry-honesty (audit D-5): the ``oneroster_csv`` profile is seeded
``PILOT_READY``. Before this adapter existed, ``get_connector("oneroster_csv")``
returned ``None`` and discovery failed with ``connector_not_registered`` — a
dead profile advertising a capability with no code behind it.

This adapter is the discovery / preview surface over the SAME OneRoster v1.2
CSV bundle the file-upload path applies via
:class:`apps.migration_cloud.accelerators.oneroster_v1p2.OneRosterV1p2InboundAccelerator`.
It delegates its per-entity column knowledge to the accelerator's
``ONEROSTER_FILE_MAP`` (single source of truth) and confirms the accelerator is
registered before it verifies a connection — so a preview here maps 1:1 onto
what the apply path will land. The heavy apply (idempotent upsert on
``sourcedId``, ``status=tobedeleted`` handling, tenant RLS scoping, quarantine,
rollback) stays with the orchestrator + accelerator; this connector NEVER writes
to tenant tables — it only reads the operator-provided export for a preview.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from apps.migration_cloud.accelerators import get_accelerator
from apps.migration_cloud.accelerators.oneroster_v1p2 import ONEROSTER_FILE_MAP

from .base import ConnectorAdapter, ConnectorCapabilities, EntityPreview

#: Vendor slug the OneRoster accelerator registers itself under.
_ACCELERATOR_SOURCE = "oneroster"

# Connector ``entity_type`` -> OneRoster bundle filename. The accelerator keys
# its map by canonical-pipeline domain names ("staff"/"sections"/"enrollment"),
# which are not the connector ``ENTITY_TYPES`` vocabulary, so we key by the
# connector's entity names here and reuse the accelerator's per-file column
# mappings (``ONEROSTER_FILE_MAP[filename][1]``) for the preview.
_ENTITY_TO_ONEROSTER_FILE: dict[str, str] = {
    "students": "students.csv",
    "teachers": "teachers.csv",
    "staff": "users.csv",
    "guardians": "parents.csv",
    "subjects": "courses.csv",
    "sections": "classes.csv",
    "classes": "classes.csv",
    "enrollments": "enrollments.csv",
}


class OneRosterCsvConnector(ConnectorAdapter):
    """Discovery/preview adapter for a OneRoster v1.2 CSV export bundle.

    Credentials may carry the export bundle as either ``export_dir`` (a folder
    holding the fixed-name OneRoster CSV files) or ``export_paths`` (a
    ``{filename: path}`` map). Absent a bundle the adapter is still registered
    and honest — it surfaces ``oneroster_export_bundle_required`` as a blocker
    rather than resolving to ``connector_not_registered``.
    """

    profile_key = "oneroster_csv"
    certification = "pilot_ready"

    def _resolve_export_file(
        self, filename: str, credentials: dict[str, Any] | None
    ) -> Path | None:
        creds = credentials or {}
        paths = creds.get("export_paths")
        if isinstance(paths, dict) and paths.get(filename):
            return Path(paths[filename])
        export_dir = creds.get("export_dir")
        if export_dir:
            candidate = Path(export_dir) / filename
            if candidate.is_file():
                return candidate
        return None

    def _bundle_provided(self, credentials: dict[str, Any] | None) -> bool:
        creds = credentials or {}
        return bool(creds.get("export_dir") or creds.get("export_paths"))

    def _supported_entities(self, credentials: dict[str, Any] | None) -> list[str]:
        """Entities the current export actually contains, else the full set."""
        creds = credentials or {}
        present: set[str] | None = None
        paths = creds.get("export_paths")
        if isinstance(paths, dict):
            present = {name for name, path in paths.items() if path}
        else:
            export_dir = creds.get("export_dir")
            if export_dir and Path(export_dir).is_dir():
                present = {p.name for p in Path(export_dir).iterdir() if p.is_file()}
        if present is None:
            return list(_ENTITY_TO_ONEROSTER_FILE.keys())
        return [
            entity
            for entity, filename in _ENTITY_TO_ONEROSTER_FILE.items()
            if filename in present
        ]

    def verify_connection(
        self, *, source_url: str, credentials: dict[str, Any] | None
    ) -> tuple[bool, list[str]]:
        if not source_url:
            return False, ["source_url_required"]
        if get_accelerator(_ACCELERATOR_SOURCE) is None:
            return False, ["oneroster_accelerator_not_registered"]
        return True, []

    def discover_capabilities(
        self, *, source_url: str, credentials: dict[str, Any] | None
    ) -> ConnectorCapabilities:
        blockers: list[str] = []
        if get_accelerator(_ACCELERATOR_SOURCE) is None:
            blockers.append("oneroster_accelerator_not_registered")
        if not self._bundle_provided(credentials):
            blockers.append("oneroster_export_bundle_required")
        return ConnectorCapabilities(
            supported_entities=self._supported_entities(credentials),
            supported_methods=["file_export"],
            external_blockers=blockers,
            certification=self.certification,
        )

    def extract_entity(
        self,
        entity_type: str,
        *,
        source_url: str,
        credentials: dict[str, Any] | None,
        limit: int = 25,
    ) -> EntityPreview:
        filename = _ENTITY_TO_ONEROSTER_FILE.get(entity_type)
        if filename is None:
            return EntityPreview(
                entity_type=entity_type,
                warnings=["entity_not_in_oneroster_bundle"],
            )
        path = self._resolve_export_file(filename, credentials)
        if path is None or not path.is_file():
            return EntityPreview(
                entity_type=entity_type,
                warnings=["oneroster_export_bundle_required"],
            )
        # Reuse the accelerator's canonical column mapping so preview field
        # names match what the apply path will land.
        _, mappings = ONEROSTER_FILE_MAP.get(filename, ("", {}))
        count = 0
        samples: list[dict[str, Any]] = []
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                count += 1
                if len(samples) < limit:
                    samples.append(
                        {mappings.get(key, key): value for key, value in row.items()}
                    )
        return EntityPreview(
            entity_type=entity_type,
            estimated_count=count,
            sample_records=samples,
        )
