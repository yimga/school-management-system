"""Browser-export workflow connector — companion extension path only.

Does NOT automate SIS login or bypass MFA/CAPTCHA. Schools use the
companion extension in their own authenticated browser session, then upload
exports through Migration Cloud intake.
"""

from __future__ import annotations

from typing import Any

from .base import ConnectorAdapter, ConnectorCapabilities, EntityPreview


class GenericBrowserExportConnector(ConnectorAdapter):
    profile_key = "generic_browser_export"
    certification = "browser_export_experimental"

    def verify_connection(self, *, source_url: str, credentials: dict[str, Any] | None) -> tuple[bool, list[str]]:
        if not source_url:
            return False, ["source_url_required"]
        return True, []

    def discover_capabilities(self, *, source_url: str, credentials: dict[str, Any] | None) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supported_entities=["students", "staff", "guardians", "enrollments", "attendance", "marks"],
            supported_methods=["username_password"],
            external_blockers=[
                "use_companion_extension_in_authenticated_browser",
                "no_automated_login_or_mfa_bypass",
            ],
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
            warnings=["use_companion_extension_then_upload_export"],
        )

    def get_external_blockers(self) -> list[str]:
        return [
            "browser_automation_limited_to_operator_authenticated_export",
            "companion_extension_required_for_live_directory_extract",
        ]
