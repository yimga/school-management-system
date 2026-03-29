"""
Batch 14 Phase 5b: legacy ``siteconfig_dynamicfield*`` models and tables are removed.

``connect_siteconfig_dynamicfield_dual_write`` remains as a no-op so ``metadata.apps`` wiring is stable.
"""

from __future__ import annotations


def connect_siteconfig_dynamicfield_dual_write() -> None:
    return
