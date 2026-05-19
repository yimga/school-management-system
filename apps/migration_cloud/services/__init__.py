"""Service-layer helpers for the Migration Cloud app.

The app historically exposed ``BundleIngestionService`` from a sibling
``services.py`` module. A later ``services/`` package is the import target for
``apps.migration_cloud.services`` now, so re-export the ingestion contract here
to keep intake views, tests, and older callers on the stable import path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_INGESTION_MODULE_NAME = "apps.migration_cloud._bundle_ingestion_service"
_INGESTION_MODULE_PATH = Path(__file__).resolve().parents[1] / "services.py"
_spec = importlib.util.spec_from_file_location(
    _INGESTION_MODULE_NAME,
    _INGESTION_MODULE_PATH,
)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load Migration Cloud ingestion service from {_INGESTION_MODULE_PATH}")

_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault(_INGESTION_MODULE_NAME, _module)
_spec.loader.exec_module(_module)

BundleIngestionService = _module.BundleIngestionService
BundleSpec = _module.BundleSpec
IngestionResult = _module.IngestionResult

__all__ = [
    "BundleIngestionService",
    "BundleSpec",
    "IngestionResult",
]
