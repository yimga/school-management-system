"""Migration Cloud connector adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


ENTITY_TYPES = (
    "schools",
    "academic_years",
    "terms",
    "grades",
    "classes",
    "sections",
    "subjects",
    "students",
    "guardians",
    "staff",
    "teachers",
    "enrollments",
    "attendance",
    "marks",
    "report_cards",
    "invoices",
    "payments",
    "behavior",
    "documents",
)


class ConnectorError(Exception):
    """Raised when a connector cannot fulfil a safe, authorized operation."""


@dataclass
class ConnectorCapabilities:
    supported_entities: list[str] = field(default_factory=list)
    supported_methods: list[str] = field(default_factory=list)
    external_blockers: list[str] = field(default_factory=list)
    certification: str = "placeholder"


@dataclass
class EntityPreview:
    entity_type: str
    estimated_count: int = 0
    sample_records: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ConnectorAdapter(ABC):
    """One adapter per source platform profile key."""

    profile_key: str = ""
    certification: str = "placeholder"

    @abstractmethod
    def verify_connection(self, *, source_url: str, credentials: dict[str, Any] | None) -> tuple[bool, list[str]]:
        """Return (ok, blockers). Must not log credentials."""

    @abstractmethod
    def discover_capabilities(self, *, source_url: str, credentials: dict[str, Any] | None) -> ConnectorCapabilities:
        """List entities and blockers without importing."""

    def list_entities(self) -> list[str]:
        return list(ENTITY_TYPES)

    def supports_entity(self, entity_type: str) -> bool:
        return entity_type in self.list_entities()

    @abstractmethod
    def extract_entity(
        self,
        entity_type: str,
        *,
        source_url: str,
        credentials: dict[str, Any] | None,
        limit: int = 25,
    ) -> EntityPreview:
        """Preview extraction — discovery only, no tenant writes."""

    def normalize_entity(self, entity_type: str, raw_record: dict[str, Any]) -> dict[str, Any]:
        return dict(raw_record)

    def get_rate_limit_policy(self) -> dict[str, Any]:
        return {"requests_per_minute": 30, "burst": 5}

    def get_external_blockers(self) -> list[str]:
        return []


_REGISTRY: dict[str, ConnectorAdapter] = {}


def register_connector(adapter: ConnectorAdapter) -> None:
    _REGISTRY[adapter.profile_key] = adapter


def get_connector(profile_key: str) -> ConnectorAdapter | None:
    return _REGISTRY.get(profile_key)


def list_connectors() -> dict[str, ConnectorAdapter]:
    return dict(_REGISTRY)
