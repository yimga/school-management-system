"""Register all connector adapters at import time."""

from __future__ import annotations

from .base import register_connector
from .generic_api import GenericAPIConnector
from .generic_browser_export import GenericBrowserExportConnector
from .generic_export import GenericExportConnector
from .vendor_export import (
    BlackbaudExportConnector,
    OAuthExportConnector,
    PowerSchoolExportConnector,
    VeracrossExportConnector,
)
from .vendor_placeholders import FinalsitePlaceholderConnector, OpenSISConnector


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
    ):
        register_connector(adapter)


bootstrap_connectors()
