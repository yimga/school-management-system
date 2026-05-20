"""Vendor export connectors — certified via synthetic CSV fixtures + accelerators."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from apps.migration_cloud.accelerators import get_accelerator

from .base import ConnectorAdapter, ConnectorCapabilities, EntityPreview

_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


class VendorExportConnector(ConnectorAdapter):
    """Export-file connector backed by vendor accelerators and repo test fixtures."""

    profile_key: str = ""
    vendor_source: str = ""
    certification: str = "pilot_ready"
    fixture_filename: str = ""

    def _fixture_path(self, credentials: dict[str, Any] | None) -> Path | None:
        if credentials and credentials.get("export_path"):
            return Path(credentials["export_path"])
        if self.fixture_filename:
            candidate = _FIXTURE_ROOT / self.fixture_filename
            if candidate.is_file():
                return candidate
        return None

    def _count_rows(self, path: Path) -> int:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return sum(1 for _ in reader)

    def _sample_rows(self, path: Path, limit: int) -> list[dict[str, Any]]:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for _, row in zip(range(limit), reader)]

    def verify_connection(
        self, *, source_url: str, credentials: dict[str, Any] | None
    ) -> tuple[bool, list[str]]:
        if not source_url:
            return False, ["source_url_required"]
        path = self._fixture_path(credentials)
        if path is None:
            return False, ["export_file_required"]
        accelerator = get_accelerator(self.vendor_source)
        if accelerator is None:
            return False, ["accelerator_not_registered"]
        return True, []

    def discover_capabilities(
        self, *, source_url: str, credentials: dict[str, Any] | None
    ) -> ConnectorCapabilities:
        path = self._fixture_path(credentials)
        entities = ["students", "staff", "guardians", "classes", "enrollments"]
        blockers: list[str] = []
        if path is None:
            blockers.append("export_file_required")
        return ConnectorCapabilities(
            supported_entities=entities,
            supported_methods=["file_export", "api_token"],
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
        path = self._fixture_path(credentials)
        if path is None:
            return EntityPreview(entity_type=entity_type, warnings=["export_file_required"])
        if entity_type != "students":
            return EntityPreview(
                entity_type=entity_type,
                estimated_count=0,
                warnings=["fixture_covers_students_entity_only_in_pilot"],
            )
        count = self._count_rows(path)
        samples = self._sample_rows(path, limit)
        return EntityPreview(
            entity_type=entity_type,
            estimated_count=count,
            sample_records=samples,
        )


class PowerSchoolExportConnector(VendorExportConnector):
    profile_key = "powerschool"
    vendor_source = "powerschool"
    fixture_filename = "synthetic_powerschool.csv"


class BlackbaudExportConnector(VendorExportConnector):
    profile_key = "blackbaud"
    vendor_source = "blackbaud"
    fixture_filename = "synthetic_blackbaud.csv"


class VeracrossExportConnector(VendorExportConnector):
    profile_key = "veracross"
    vendor_source = "veracross"
    fixture_filename = "synthetic_veracross.csv"


class OAuthExportConnector(VendorExportConnector):
    """OAuth path uses export fallback until live Google Classroom API is certified."""

    profile_key = "google_classroom"
    vendor_source = "runmycampus_canonical"
    certification = "api_experimental"
    fixture_filename = ""

    def verify_connection(
        self, *, source_url: str, credentials: dict[str, Any] | None
    ) -> tuple[bool, list[str]]:
        if not source_url:
            return False, ["source_url_required"]
        if not (credentials or {}).get("oauth_token"):
            return False, ["oauth_token_required"]
        return True, []

    def discover_capabilities(
        self, *, source_url: str, credentials: dict[str, Any] | None
    ) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supported_entities=["students", "classes"],
            supported_methods=["oauth", "file_export"],
            external_blockers=["live_google_classroom_api_not_certified_use_export_fallback"],
            certification=self.certification,
        )
