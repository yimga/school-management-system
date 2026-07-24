"""Register all connector adapters at import time.

Built-in connectors are registered from the fixed tuple below. In addition,
:func:`bootstrap_connectors` discovers *plugin* connectors so a partner package
can register a connector WITHOUT a core deploy — via
``settings.MIGRATION_CLOUD_CONNECTOR_PLUGINS`` or the
``runmycampus.migration_connectors`` entry-point group (see
:mod:`apps.migration_cloud.connectors.plugin_loader`). A broken plugin is
isolated + skipped there; the outer guard here is belt-and-suspenders so plugin
discovery can never crash bootstrap or take down the built-in connectors.
"""

from __future__ import annotations

import logging

from .base import register_connector
from .generic_api import GenericAPIConnector
from .generic_browser_export import GenericBrowserExportConnector
from .generic_export import GenericExportConnector
from .oneroster_csv import OneRosterCsvConnector
from .plugin_loader import load_plugin_connectors
from .vendor_export import (
    BlackbaudExportConnector,
    OAuthExportConnector,
    PowerSchoolExportConnector,
    VeracrossExportConnector,
)
from .vendor_placeholders import FinalsitePlaceholderConnector, OpenSISConnector

logger = logging.getLogger(__name__)


def bootstrap_connectors() -> None:
    for adapter in (
        GenericExportConnector(),
        GenericAPIConnector(),
        GenericBrowserExportConnector(),
        PowerSchoolExportConnector(),
        BlackbaudExportConnector(),
        VeracrossExportConnector(),
        OAuthExportConnector(),
        FinalsitePlaceholderConnector(),
        OpenSISConnector(),
        OneRosterCsvConnector(),
    ):
        register_connector(adapter)

    # Marketplace-extensible discovery (audit D-5 / D-7).
    try:
        for adapter in load_plugin_connectors():
            register_connector(adapter)
    except Exception:  # noqa: BLE001 — plugin discovery must never break core bootstrap
        logger.warning(
            "migration_cloud.connectors: plugin discovery failed; built-ins intact"
        )


bootstrap_connectors()
