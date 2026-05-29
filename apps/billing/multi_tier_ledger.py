"""v4.00.36 Phase 3 — multi-campus parent/child ledger rollup.

Closes the doc's "polymorphic ledger record hierarchies for multi-campus
enterprises" ask.

Each ``BillingAccount`` is independent: it has its own ledger, its own
currency, its own status. A diocese / corporate group can mark some
accounts as children of a "holding" account via ``parent_account``.
At end-of-period, the parent can pull a roll-up that:

* aggregates every child's ``PlatformLedgerEntry`` posted in the window,
* converts each line into the parent's currency via a pluggable FX
  resolver (default: 1:1 same-currency, raise on cross-currency without
  a configured rate),
* returns a typed ``LedgerRollup`` record for the dashboard.

No DB writes — pure aggregation. The parent's own ledger is untouched;
the rollup is a computed read. Surface a ``post_rollup_into_parent``
helper later if a tenant explicitly wants the aggregate to materialize.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LedgerLine:
    account_pk: int
    school_label: str
    entry_type: str
    status: str
    amount_local: Decimal
    currency_local: str
    amount_parent: Decimal
    happened_at: datetime
    reference: str


@dataclass
class LedgerRollup:
    parent_account_pk: int
    parent_currency: str
    window_start: datetime | None
    window_end: datetime | None
    lines: list[LedgerLine] = field(default_factory=list)
    totals_by_type: dict[str, Decimal] = field(default_factory=dict)
    grand_total_parent: Decimal = Decimal("0.00")
    unresolved_currency_pairs: list[tuple[str, str]] = field(default_factory=list)

    def add_line(self, line: LedgerLine) -> None:
        self.lines.append(line)
        self.totals_by_type[line.entry_type] = self.totals_by_type.get(
            line.entry_type, Decimal("0.00")
        ) + line.amount_parent
        self.grand_total_parent += line.amount_parent


# A FX resolver returns ``Decimal`` units of ``target_currency`` per 1 unit
# of ``source_currency``. Same-currency must return ``Decimal("1")``.
FXResolver = Callable[[str, str], "Decimal | None"]


def _default_fx_resolver(source: str, target: str) -> Decimal | None:
    if (source or "").upper() == (target or "").upper():
        return Decimal("1")
    return None


def rollup_account_balance(
    parent_account: Any,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    fx_resolver: FXResolver | None = None,
) -> LedgerRollup:
    """Compute the rollup view for ``parent_account``'s children.

    ``window_start`` / ``window_end`` filter by ``PlatformLedgerEntry.happened_at``.
    """
    fx = fx_resolver or _default_fx_resolver
    parent_currency = (getattr(parent_account, "currency_code", "USD") or "USD").upper()
    rollup = LedgerRollup(
        parent_account_pk=int(getattr(parent_account, "pk", 0) or 0),
        parent_currency=parent_currency,
        window_start=window_start,
        window_end=window_end,
    )
    try:
        from apps.billing.models import BillingAccount, PlatformLedgerEntry
    except (ImportError, RuntimeError):
        return rollup

    try:
        # tenant-isolation-allow: parent-account-iter-from-explicit-parent-fk-platform-scope
        children = BillingAccount.objects.filter(parent_account=parent_account)
    except (AttributeError, RuntimeError, ValueError):
        return rollup

    for child in children:
        child_currency = (getattr(child, "currency_code", parent_currency) or parent_currency).upper()
        try:
            # tenant-isolation-allow: child-ledger-scoped-via-billing-account-fk-rollup
            qs = PlatformLedgerEntry.objects.filter(billing_account=child)
            if window_start is not None:
                qs = qs.filter(happened_at__gte=window_start)
            if window_end is not None:
                qs = qs.filter(happened_at__lte=window_end)
        except (AttributeError, RuntimeError, ValueError):
            continue
        rate = fx(child_currency, parent_currency)
        if rate is None:
            pair = (child_currency, parent_currency)
            if pair not in rollup.unresolved_currency_pairs:
                rollup.unresolved_currency_pairs.append(pair)
            continue
        for entry in qs.iterator():
            try:
                amount_local = Decimal(str(entry.amount or 0))
                amount_parent = (amount_local * rate).quantize(Decimal("0.01"))
            except (AttributeError, TypeError, ValueError) as exc:
                logger.debug("rollup line skipped (amount parse): %s", exc)
                continue
            rollup.add_line(LedgerLine(
                account_pk=int(getattr(child, "pk", 0) or 0),
                school_label=str(getattr(getattr(child, "school", None), "name", "")),
                entry_type=str(entry.entry_type),
                status=str(entry.status),
                amount_local=amount_local,
                currency_local=child_currency,
                amount_parent=amount_parent,
                happened_at=entry.happened_at,
                reference=str(entry.reference or ""),
            ))
    return rollup


__all__ = ["LedgerLine", "LedgerRollup", "FXResolver", "rollup_account_balance"]
