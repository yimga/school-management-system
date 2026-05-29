"""v4.00.36 Phase 3 — pluggable tax-rate resolver.

The doc's "review tax API integration" ask: schools should be able to
plug a live tax engine (Avalara, TaxJar, Stripe Tax) when the static
``CountryMultiplier.tax_rate`` is too coarse — e.g. a US state-level
sales tax that varies by ZIP, or a Canadian PST that varies by province.

This module ships:

* A registry: ``register_tax_resolver(name, callable)`` /
  ``set_active_resolver(name)``;
* A canonical interface: ``resolver(country_code, region_code, *,
  subdivision_code=None, line_amount=None) -> Decimal | None``;
* A static fallback ``static_tax_resolver`` that reads the
  ``CountryMultiplier.tax_rate`` field (the Phase 1 source of truth);
* ``resolve_tax_rate(country_code, **kwargs) -> Decimal`` that runs the
  active resolver and falls back to the static one when the resolver
  returns ``None``.

Resolvers are pure functions of their arguments — they never write to
the DB. Plug a live engine by writing a small adapter module that
calls the engine's REST API and returns a ``Decimal`` rate.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)


class TaxResolver(Protocol):
    def __call__(
        self,
        country_code: str,
        *,
        subdivision_code: str | None = None,
        line_amount: Decimal | None = None,
    ) -> Decimal | None: ...


_RESOLVERS: dict[str, TaxResolver] = {}
_ACTIVE_NAME: str = "static"


def register_tax_resolver(name: str, resolver: TaxResolver) -> None:
    if not name:
        return
    _RESOLVERS[name] = resolver


def set_active_resolver(name: str) -> None:
    global _ACTIVE_NAME
    if not name or name not in _RESOLVERS:
        return
    _ACTIVE_NAME = name


def active_resolver_name() -> str:
    return _ACTIVE_NAME


def static_tax_resolver(
    country_code: str,
    *,
    subdivision_code: str | None = None,  # noqa: ARG001 — interface symmetry
    line_amount: Decimal | None = None,  # noqa: ARG001
) -> Decimal | None:
    """Read ``CountryMultiplier.tax_rate`` for the country."""
    if not country_code:
        return None
    try:
        from apps.siteconfig.models_platform_catalog import CountryMultiplier
    except (ImportError, RuntimeError):
        return None
    try:
        # tenant-isolation-allow: country-multiplier-platform-catalog-tax-resolver
        row = CountryMultiplier.objects.filter(
            country_code__iexact=country_code, is_active=True
        ).only("tax_rate").first()
    except (AttributeError, RuntimeError, ValueError):
        return None
    if row is None:
        return None
    try:
        rate = Decimal(str(row.tax_rate or 0))
    except (TypeError, ValueError):
        return None
    return rate


# Always available.
register_tax_resolver("static", static_tax_resolver)


def resolve_tax_rate(
    country_code: str,
    *,
    subdivision_code: str | None = None,
    line_amount: Decimal | None = None,
) -> Decimal:
    """Return the effective tax rate for the request.

    Tries the active resolver, falls back to the static resolver if the
    active one returns ``None``. Returns ``Decimal("0")`` when nothing
    resolves so callers never receive ``None`` and accidentally treat
    it as a numeric.
    """
    active = _RESOLVERS.get(_ACTIVE_NAME) or static_tax_resolver
    try:
        rate = active(
            country_code,
            subdivision_code=subdivision_code,
            line_amount=line_amount,
        )
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        logger.debug("active tax resolver %s failed: %s", _ACTIVE_NAME, exc)
        rate = None
    if rate is None and _ACTIVE_NAME != "static":
        try:
            rate = static_tax_resolver(country_code)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            rate = None
    return rate or Decimal("0")


__all__ = [
    "TaxResolver",
    "register_tax_resolver",
    "set_active_resolver",
    "active_resolver_name",
    "static_tax_resolver",
    "resolve_tax_rate",
]
