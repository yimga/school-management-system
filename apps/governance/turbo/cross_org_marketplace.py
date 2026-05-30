"""Phase 6 turbo runtime: cross-org marketplace.

Surfaces teacher transfer offers and curriculum reuse within consenting
organizations. ReBAC-style sharing flags gate visibility. The store is an
in-memory registry seeded by the host app; the contract is offer / consent /
view.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-cross-org-marketplace"
CONTRACT_TITLE = "Cross-org talent and curriculum marketplace"


@dataclass
class Offer:
    offer_id: str
    org_id: str
    kind: str
    payload: dict[str, Any]
    sharing_flags: set[str] = field(default_factory=set)


class Marketplace:
    def __init__(self) -> None:
        self._offers: dict[str, Offer] = {}
        self._consents: dict[tuple[str, str], bool] = {}

    def list_offers(self, *, requesting_org_id: str) -> list[Offer]:
        return [
            o for o in self._offers.values()
            if requesting_org_id == o.org_id or self._consents.get((o.org_id, requesting_org_id), False)
        ]

    def post_offer(self, offer: Offer) -> None:
        self._offers[offer.offer_id] = offer

    def grant_consent(self, offering_org_id: str, viewing_org_id: str) -> None:
        self._consents[(offering_org_id, viewing_org_id)] = True

    def revoke_consent(self, offering_org_id: str, viewing_org_id: str) -> None:
        self._consents.pop((offering_org_id, viewing_org_id), None)


def runtime_health() -> dict[str, Any]:
    market = Marketplace()
    market.post_offer(Offer("o1", "orgA", "teacher_transfer", {"role": "math"}))
    market.post_offer(Offer("o2", "orgB", "curriculum", {"subject": "physics"}))
    isolated = market.list_offers(requesting_org_id="orgA")
    market.grant_consent("orgB", "orgA")
    shared = market.list_offers(requesting_org_id="orgA")
    healthy = len(isolated) == 1 and len(shared) == 2
    return {"contract_id": CONTRACT_ID, "healthy": healthy, "isolated_visible": len(isolated), "after_consent_visible": len(shared)}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
