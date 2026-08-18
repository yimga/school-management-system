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


# --------------------------------------------------------------------------- #
# Entity-type resolution (B5)
# --------------------------------------------------------------------------- #
# A live source names its own entities. Matching them against ENTITY_TYPES by exact
# string membership meant "Students", "Student", or "Report Cards" resolved to nothing —
# and the discovery loop's `continue` then dropped that WHOLE DOMAIN with no warning, no
# error and no quarantine row, so the operator saw a clean-looking result that was simply
# missing data. This is the same recall gap the FILE path closed by reusing the mapper's
# containment scorer; the connector path had been left on exact-membership.
#
# Resolution here is deliberately MORPHOLOGICAL ONLY — case, punctuation/separator and
# singular/plural. It does NOT guess semantically, because ENTITY_TYPES contains both
# `grades` (grade LEVELS) and `marks` (scores): a synonym table that mapped "grades" to
# "marks" would silently mis-route scores into levels, turning a recall bug into a
# correctness bug. A name we cannot resolve morphologically is REPORTED, never guessed.
def _split_camel_case(text: str) -> str:
    """``ReportCards`` -> ``Report Cards``; ``IDNumber`` -> ``ID Number``.

    Connector APIs (OneRoster and most REST vendors) report camelCase entity names, so
    without this a name with no separator at all normalizes to one long token and resolves
    to nothing.
    """
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch.isupper() and i > 0:
            prev = text[i - 1]
            nxt = text[i + 1] if i + 1 < len(text) else ""
            # boundary after a lowercase/digit, or the last capital of an acronym run
            if prev.islower() or prev.isdigit() or (prev.isupper() and nxt.islower()):
                out.append(" ")
        out.append(ch)
    return "".join(out)


def normalize_entity_key(value: object) -> str:
    """``"  Report Cards "`` / ``"report-cards"`` / ``"ReportCards"`` -> ``report_cards``."""
    text = _split_camel_case(str(value or "")).lower()
    return "_".join("".join(c if c.isalnum() else " " for c in text).split())


def _singularize(key: str) -> str:
    if key.endswith("ies"):
        return key[:-3] + "y"
    if key.endswith("sses"):
        return key[:-2]
    if key.endswith("s") and not key.endswith("ss"):
        return key[:-1]
    return key


def _build_entity_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical in ENTITY_TYPES:
        key = normalize_entity_key(canonical)
        for variant in (key, _singularize(key)):
            # First writer wins so a canonical name can never be shadowed by another
            # entity's singular form.
            index.setdefault(variant, canonical)
    return index


_ENTITY_INDEX = _build_entity_index()


def resolve_entity_type(candidate: object) -> str | None:
    """The canonical ENTITY_TYPES member for a source's own entity name, or None.

    Returning the CANONICAL name matters as much as matching: downstream code looks rows
    up by canonical key, so echoing the vendor's spelling back would fail later instead of
    here.
    """
    key = normalize_entity_key(candidate)
    if not key:
        return None
    return _ENTITY_INDEX.get(key) or _ENTITY_INDEX.get(_singularize(key))


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
        """True when the source's own entity name resolves to one this adapter serves.

        Tolerant by design (see ``resolve_entity_type``): a vendor's ``"Students"`` or a
        hand-typed ``"student"`` must not be read as "this source has no students".
        """
        resolved = resolve_entity_type(entity_type)
        return resolved is not None and resolved in self.list_entities()

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
