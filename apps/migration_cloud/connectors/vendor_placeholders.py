"""Vendor-specific connector placeholders — honest certification only."""

from __future__ import annotations

from typing import Any

from .base import ConnectorAdapter, ConnectorCapabilities, EntityPreview


class _VendorPlaceholder(ConnectorAdapter):
    certification = "placeholder"
    _vendor_blocker: str = "vendor_connector_not_certified"

    def verify_connection(self, *, source_url: str, credentials: dict[str, Any] | None) -> tuple[bool, list[str]]:
        if not source_url:
            return False, ["source_url_required"]
        return True, [self._vendor_blocker]

    def discover_capabilities(self, *, source_url: str, credentials: dict[str, Any] | None) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supported_entities=["students", "staff"],
            supported_methods=["file_export"],
            external_blockers=[self._vendor_blocker, "use_manual_export_or_companion"],
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
            warnings=[self._vendor_blocker],
        )


class PowerSchoolPlaceholderConnector(_VendorPlaceholder):
    profile_key = "powerschool"
    certification = "file_export_only"


class BlackbaudPlaceholderConnector(_VendorPlaceholder):
    profile_key = "blackbaud"
    certification = "file_export_only"


class VeracrossPlaceholderConnector(_VendorPlaceholder):
    profile_key = "veracross"
    certification = "file_export_only"


class FinalsitePlaceholderConnector(_VendorPlaceholder):
    profile_key = "finalsite"
    certification = "planned"


class GoogleClassroomPlaceholderConnector(_VendorPlaceholder):
    profile_key = "google_classroom"
    certification = "planned"

    def discover_capabilities(self, *, source_url: str, credentials: dict[str, Any] | None) -> ConnectorCapabilities:
        caps = super().discover_capabilities(source_url=source_url, credentials=credentials)
        caps.supported_methods = ["oauth"]
        caps.external_blockers.append("oauth_connector_planned_not_live")
        return caps


class OpenSISConnector(_VendorPlaceholder):
    profile_key = "open_sis"
    certification = "file_export_only"
