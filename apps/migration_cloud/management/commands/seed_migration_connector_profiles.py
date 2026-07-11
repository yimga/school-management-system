"""Seed MigrationConnectorProfile registry rows."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.migration_cloud.models_connectors import (
    ConnectorCertificationStatus,
    MigrationConnectorProfile,
)

PROFILES = [
    {
        "key": "generic_csv_export",
        "display_name": "Generic CSV / Excel export",
        "vendor_name": "Any",
        "supported_methods": ["file_export", "manual_template"],
        "supports_api": False,
        "supports_export": True,
        "supports_browser_export": False,
        "certification_status": ConnectorCertificationStatus.PRODUCTION_READY,
        "supported_entities": ["students", "teachers", "guardians", "classes", "invoices", "receipts"],
    },
    {
        "key": "oneroster_csv",
        "display_name": "OneRoster CSV",
        "vendor_name": "IMS Global",
        "supported_methods": ["file_export"],
        "certification_status": ConnectorCertificationStatus.PILOT_READY,
        "supported_entities": ["students", "teachers", "classes", "enrollments"],
    },
    {
        "key": "generic_api",
        "display_name": "Generic API (token)",
        "supported_methods": ["api_token"],
        "supports_api": True,
        "certification_status": ConnectorCertificationStatus.EXPERIMENTAL,
    },
    {
        "key": "generic_browser_export",
        "display_name": "Browser export (Companion)",
        "supported_methods": ["username_password"],
        "supports_browser_export": True,
        "certification_status": ConnectorCertificationStatus.EXPERIMENTAL,
    },
    {
        "key": "powerschool",
        "display_name": "PowerSchool",
        "vendor_name": "PowerSchool",
        "supported_methods": ["file_export", "api_token"],
        "certification_status": ConnectorCertificationStatus.PILOT_READY,
        "known_limitations": "Pilot verified via synthetic CSV fixtures; live API not certified.",
    },
    {
        "key": "blackbaud",
        "display_name": "Blackbaud",
        "supported_methods": ["file_export"],
        "certification_status": ConnectorCertificationStatus.PILOT_READY,
    },
    {
        "key": "veracross",
        "display_name": "Veracross",
        "supported_methods": ["file_export"],
        "certification_status": ConnectorCertificationStatus.PILOT_READY,
    },
    {
        "key": "open_sis",
        "display_name": "openSIS",
        "supported_methods": ["file_export"],
        "certification_status": ConnectorCertificationStatus.EXPERIMENTAL,
    },
    {
        "key": "finalsite",
        "display_name": "Finalsite",
        "certification_status": ConnectorCertificationStatus.PLANNED,
    },
    {
        "key": "google_classroom",
        "display_name": "Google Classroom",
        "supported_methods": ["oauth", "file_export"],
        "supports_api": True,
        "certification_status": ConnectorCertificationStatus.EXPERIMENTAL,
        "known_limitations": "OAuth token gate only; live Classroom API not certified.",
    },
    {
        "key": "edfi",
        "display_name": "Ed-Fi API",
        "supported_methods": ["api_token", "oauth"],
        "supports_api": True,
        "certification_status": ConnectorCertificationStatus.PLANNED,
    },
]


def seed_connector_profiles(model=None) -> tuple[int, int]:
    """Idempotently upsert the connector registry from ``PROFILES``.

    ``model`` is the ``MigrationConnectorProfile`` class to write against —
    the live model by default, or the historical model passed by the data
    migration (``0035_seed_connector_profiles``). Keeping this a plain
    function is what lets the migration and the management command share one
    source of truth so the two can never drift. Returns ``(total, created)``.
    """
    if model is None:
        model = MigrationConnectorProfile
    created = 0
    for row in PROFILES:
        _, was_created = model.objects.update_or_create(
            key=row["key"],
            defaults={
                "display_name": row["display_name"],
                "vendor_name": row.get("vendor_name", ""),
                "supported_methods": row.get("supported_methods", []),
                "supports_api": row.get("supports_api", False),
                "supports_export": row.get("supports_export", True),
                "supports_browser_export": row.get("supports_browser_export", False),
                "certification_status": row.get(
                    "certification_status", ConnectorCertificationStatus.PLANNED
                ),
                "supported_entities": row.get("supported_entities", []),
                "known_limitations": row.get("known_limitations", ""),
                "active": True,
            },
        )
        if was_created:
            created += 1
    return len(PROFILES), created


class Command(BaseCommand):
    help = "Seed Migration Cloud connector profiles."

    def handle(self, *args, **options):
        total, created = seed_connector_profiles()
        self.stdout.write(self.style.SUCCESS(f"Seeded {total} profiles ({created} new)."))
