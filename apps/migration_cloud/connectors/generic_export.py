"""Generic file-export connector — production_ready for CSV/Excel uploads."""

from __future__ import annotations

from typing import Any

from .base import ConnectorAdapter, ConnectorCapabilities, ConnectorError, EntityPreview


class GenericExportConnector(ConnectorAdapter):
    profile_key = "generic_csv_export"
    certification = "production_ready"

    def verify_connection(self, *, source_url: str, credentials: dict[str, Any] | None) -> tuple[bool, list[str]]:
        if not source_url and not (credentials or {}).get("export_ready"):
            return False, ["export_file_or_url_required"]
        return True, []

    def discover_capabilities(self, *, source_url: str, credentials: dict[str, Any] | None) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supported_entities=["students", "teachers", "guardians", "classes", "invoices", "receipts"],
            supported_methods=["file_export", "manual_template"],
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
        samples = (credentials or {}).get("sample_rows", {}).get(entity_type, [])
        return EntityPreview(
            entity_type=entity_type,
            estimated_count=len(samples),
            sample_records=samples[:limit],
            warnings=[] if samples else ["no_export_samples_for_entity"],
        )


class GenericExportConnectorError(ConnectorError):
    pass
