"""v4.00.36 Phase 3 — PSP routing + automatic fallback chain.

Closes the doc's "fail-safe fallback subscription architectures" ask.

Given a request triple ``(country_code, currency, capability)``, this
module reads the existing ``psp_adapter_registry`` and returns an
ordered list of PSP candidates — best match first, fallbacks after.

Ranking (descending priority):

1. **Status** — ``live`` outranks ``in_progress`` outranks ``planned``.
2. **Capability** — adapters that declare the requested capability
   (cards / mobile_money / bank_transfer / payouts / refunds / 3ds /
   webhooks / recurring / marketplace_split) outrank those that don't.
3. **Currency** — adapters that settle into the requested currency
   outrank those that don't.
4. **Region** — adapters whose region matches the country's region
   outrank those that don't.
5. **Slug alphabetical** — final tiebreaker so results are deterministic.

The caller decides what to do with the chain: try-in-order with
fail-over (the doc's "switch to cash voucher when CARD is down" flow),
or just pick ``chain[0]`` for the primary attempt.

Pure: no DB writes, no network. Two registry reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .psp_adapter_registry import PSP_REGISTER, PSPRow


# Country → region buckets. Used as a soft signal in routing only;
# never as an authoritative residency map. (For residency, see
# apps.schools.School.data_region.)
_COUNTRY_REGION_HINT: dict[str, str] = {
    # africa
    "NG": "africa", "GH": "africa", "KE": "africa", "ZA": "africa", "UG": "africa",
    "TZ": "africa", "RW": "africa", "ET": "africa", "EG": "africa", "TG": "africa",
    "BJ": "africa", "CM": "africa", "CI": "africa", "SN": "africa", "ML": "africa",
    "BF": "africa", "NE": "africa", "MA": "africa", "TN": "africa", "DZ": "africa",
    "LR": "africa", "GM": "africa", "SL": "africa", "ZW": "africa", "ZM": "africa",
    "MZ": "africa", "AO": "africa", "MG": "africa", "SO": "africa", "ER": "africa",
    "DJ": "africa", "SS": "africa", "MW": "africa", "BW": "africa", "NA": "africa",
    "LS": "africa", "SZ": "africa", "GW": "africa", "CV": "africa", "ST": "africa",
    "TL": "africa", "CG": "africa", "CD": "africa", "GN": "africa", "GA": "africa",
    "TD": "africa", "CF": "africa",
    # emea
    "GB": "emea", "DE": "emea", "FR": "emea", "ES": "emea", "IT": "emea",
    "PT": "emea", "IE": "emea", "NL": "emea", "BE": "emea", "CH": "emea",
    "AT": "emea", "PL": "emea", "SE": "emea", "DK": "emea", "FI": "emea",
    "NO": "emea", "GR": "emea", "RO": "emea", "BG": "emea", "AE": "emea",
    "SA": "emea", "IL": "emea", "TR": "emea",
    # apac
    "IN": "apac", "ID": "apac", "VN": "apac", "TH": "apac", "PH": "apac",
    "MY": "apac", "SG": "apac", "BD": "apac", "PK": "apac", "JP": "apac",
    "KR": "apac", "CN": "apac", "AU": "apac", "NZ": "apac",
    # americas
    "US": "americas", "CA": "americas", "MX": "americas", "BR": "americas",
    "AR": "americas", "CL": "americas", "CO": "americas", "PE": "americas",
    "UY": "americas",
}


@dataclass(frozen=True)
class PSPCandidate:
    psp: PSPRow
    score: int
    matched_capability: bool
    matched_currency: bool
    matched_region: bool


def _country_region(country_code: str) -> str:
    return _COUNTRY_REGION_HINT.get((country_code or "").upper(), "global")


_STATUS_SCORE = {"live": 1000, "in_progress": 100, "planned": 1}


def rank_psps(
    *,
    country_code: str,
    currency: str,
    capability: str,
    eligible_statuses: Sequence[str] = ("live", "in_progress"),
    registry: Sequence[PSPRow] = PSP_REGISTER,
) -> list[PSPCandidate]:
    """Return PSP candidates ranked best-first for the request triple."""
    country_code = (country_code or "").upper()
    currency = (currency or "").upper()
    capability = (capability or "").lower()
    region = _country_region(country_code)
    statuses = set(eligible_statuses or ())
    candidates: list[PSPCandidate] = []
    for psp in registry:
        if statuses and psp.adapter_status not in statuses:
            continue
        cap_match = bool(capability) and capability in {c.lower() for c in psp.capabilities}
        currency_match = (
            bool(currency) and currency in {c.upper() for c in psp.settlement_currencies}
        )
        region_match = (region == psp.region) or (psp.region == "global")
        score = _STATUS_SCORE.get(psp.adapter_status, 0)
        if cap_match:
            score += 500
        if currency_match:
            score += 300
        if region_match:
            score += 100
        candidates.append(
            PSPCandidate(
                psp=psp,
                score=score,
                matched_capability=cap_match,
                matched_currency=currency_match,
                matched_region=region_match,
            )
        )
    candidates.sort(key=lambda c: (-c.score, c.psp.psp_slug))
    return candidates


def route_payment(
    *,
    country_code: str,
    currency: str,
    capability: str = "cards",
    fallback_capabilities: Sequence[str] = ("mobile_money", "bank_transfer"),
) -> dict[str, list[PSPCandidate]]:
    """Pick a primary PSP + a fallback chain.

    Returns ``{primary: [...], fallback: [...]}``. The fallback chain is
    computed by re-ranking under each of ``fallback_capabilities`` in
    order, then de-duplicating against the primary list. Useful for the
    doc's "card down → mobile money → cash voucher" cascade.
    """
    primary = rank_psps(country_code=country_code, currency=currency, capability=capability)
    seen = {c.psp.psp_slug for c in primary}
    fallback: list[PSPCandidate] = []
    for fallback_cap in fallback_capabilities:
        for cand in rank_psps(
            country_code=country_code, currency=currency, capability=fallback_cap
        ):
            if cand.psp.psp_slug in seen:
                continue
            seen.add(cand.psp.psp_slug)
            fallback.append(cand)
    return {"primary": primary, "fallback": fallback}


__all__ = ["PSPCandidate", "rank_psps", "route_payment"]
