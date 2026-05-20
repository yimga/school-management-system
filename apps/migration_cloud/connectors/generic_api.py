"""Generic API token connector — experimental until vendor-tested."""

from __future__ import annotations

from typing import Any

from .base import ConnectorAdapter, ConnectorCapabilities, EntityPreview


class GenericAPIConnector(ConnectorAdapter):
    profile_key = "generic_api"
    certification = "api_experimental"

    def verify_connection(self, *, source_url: str, credentials: dict[str, Any] | None) -> tuple[bool, list[str]]:
        if not source_url:
            return False, ["source_url_required"]
        if not (credentials or {}).get("api_token"):
            return False, ["api_token_required"]
        return True, []

    def discover_capabilities(self, *, source_url: str, credentials: dict[str, Any] | None) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supported_entities=["students", "staff", "classes", "enrollments"],
            supported_methods=["api_token"],
            external_blockers=["vendor_api_must_be_official_and_authorized"],
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
        return EntityPreview(
            entity_type=entity_type,
            estimated_count=0,
            sample_records=[],
            warnings=["api_pull_not_live_use_file_export_fallback"],
        )

    def get_external_blockers(self) -> list[str]:
        return ["live_api_pull_requires_vendor_certification"]
