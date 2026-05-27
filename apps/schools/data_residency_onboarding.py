"""Apply regulatory data region at school create (Glocal program batch 1530)."""

from __future__ import annotations

import logging
from typing import Any

from apps.schools.data_residency import derive_default_region, effective_region
from apps.schools.data_residency_settings import set_data_residency_payload

logger = logging.getLogger(__name__)


def apply_data_residency_for_new_school(school, *, source: str = "signup") -> dict[str, Any]:
    """
    Derive and persist ``School.data_region`` + settings payload.

    Does not save the school — caller must save if fields were updated after create.
    """
    country = (getattr(school, "country_code", None) or "").strip().upper()
    region = derive_default_region(country)
    if not getattr(school, "data_region", None):
        school.data_region = region
    set_data_residency_payload(
        school,
        {
            "region_code": effective_region(school) or region,
            "enforcement": "audit",
            "corridor_id": "",
        },
    )
    payload = {
        "source": source,
        "country_code": country,
        "data_region": school.data_region,
        "aligned": True,
    }
    logger.info(
        "data_residency_assigned source=%s region=%s country=%s school_id=%s",
        source,
        school.data_region,
        country[:2] if country else "",
        getattr(school, "pk", None),
    )
    return payload


__all__ = ["apply_data_residency_for_new_school"]
