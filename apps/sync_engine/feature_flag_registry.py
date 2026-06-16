"""Canonical registry of known tenant feature flags (owner-decision d).

``compile_manifest`` accepted ANY feature_flag key, so a typo (e.g.
``enable_offline_quee``) silently compiled into the manifest and did nothing —
no error, no warning. This is the SOT of valid flag keys, DERIVED from the
offline-mode bundle (``OFFLINE_MODE_BACKEND_FLAG_UPDATES``) so it can never drift
from the real flags, plus an explicit extension set for non-offline flags.

``compile_manifest`` validates against this: lenient by default (warns on
unknown keys so a typo is visible) with opt-in strict mode (raises). Callers that
control their flag set (the production offline-manifest builder) can pass
``strict_feature_flags=True``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Master switch + any non-offline platform flags that are legitimate manifest
# keys but not part of the offline bundle. Extend here as real flags are added.
_EXTRA_KNOWN_FLAGS: frozenset[str] = frozenset({"enable_offline_mode"})


def _bundle_bool_flags() -> set[str]:
    try:
        from apps.platform_runtime.offline_mode_bundle import (
            OFFLINE_MODE_BACKEND_FLAG_UPDATES,
        )

        return {
            str(k)
            for k, v in OFFLINE_MODE_BACKEND_FLAG_UPDATES.items()
            if isinstance(v, bool)
        }
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        logger.debug("offline bundle flags unavailable for registry", exc_info=True)
        return set()


def known_feature_flags() -> frozenset[str]:
    """The canonical set of valid feature-flag keys (bundle SOT + extras)."""
    return frozenset(_bundle_bool_flags() | set(_EXTRA_KNOWN_FLAGS))


def validate_feature_flags(flags) -> list[str]:
    """Return the sorted list of UNKNOWN flag keys present in ``flags``."""
    known = known_feature_flags()
    return sorted(str(k) for k in (flags or {}) if str(k) not in known)
