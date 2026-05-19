"""Analytics services package.

Re-exports the legacy ``apps/analytics/services.py`` module so existing
``from apps.analytics.services import …`` imports keep working alongside
subpackage modules (e.g. ``tenant_overview_viz``).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_LEGACY_PATH = Path(__file__).resolve().parent.parent / "services.py"
_LEGACY_MODULE = "apps.analytics._legacy_services_py"


def _legacy_module():
    cached = sys.modules.get(_LEGACY_MODULE)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_LEGACY_MODULE, _LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load legacy analytics services from {_LEGACY_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE] = mod
    spec.loader.exec_module(mod)
    return mod


_legacy = _legacy_module()

__all__ = [name for name in dir(_legacy) if not name.startswith("_")]
globals().update({name: getattr(_legacy, name) for name in __all__})
