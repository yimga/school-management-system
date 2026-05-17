"""Decimal-aware JSON helpers for finance / billing / marketplace.

Seven-pillar audit P5 follow-up. The platform stores money as
``DecimalField`` (12 digits, 2 decimal places) but serializes through
``json.dumps``, which forces a Python float and loses precision on edge
values (e.g. ``Decimal("0.1") + Decimal("0.2")`` survives Decimal
arithmetic exactly but round-trips through float as ``0.30000000000000004``).

This module gives finance / billing / marketplace code two precise
serialization options:

* :func:`amount_str` — render a ``Decimal`` (or numeric str / int)
  as a precision-preserving string (``"123.45"``). Use when wire
  format flexibility is acceptable.
* :class:`DecimalJSONEncoder` — a ``json.JSONEncoder`` subclass that
  emits ``Decimal`` as numeric strings without going through float.
  Pass via ``json.dumps(payload, cls=DecimalJSONEncoder)``.

Why not just convert to ``float``? IEEE 754 doesn't represent all
two-decimal currency values exactly. The bug only surfaces when sums
or comparisons cross a half-cent boundary, but when it does, ledger
totals drift and reconciliation fails. Use these helpers on every
money path in ``apps/finance/``, ``apps/billing/``, ``apps/marketplace/``,
and ``payment/``.

Sites where ``float()`` is still legitimate (ratios, percentages,
gateway-int-cents inputs) must carry a ``# money-float-allow: <reason>``
marker on the same line, recognized by ``scripts/scan_money_float.py``.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


# Quantization step used across the platform for currency display.
# Keep in lock-step with the ``DecimalField(max_digits=12, decimal_places=2)``
# canonical money column in ``apps/finance/models.py``.
_AMOUNT_QUANT = Decimal("0.01")


def amount_str(value: Any, *, quantize: bool = True) -> str:
    """Return a precision-preserving string for a monetary value.

    Accepts ``Decimal`` (canonical), ``int``, ``str``, or ``None``.
    Floats are accepted but a warning-free coerce — the caller is
    responsible for not having lost precision before reaching here.

    >>> amount_str(Decimal("123.4"))
    '123.40'
    >>> amount_str(Decimal("0.1") + Decimal("0.2"))
    '0.30'
    >>> amount_str(None)
    '0.00'
    """
    if value is None:
        value = Decimal("0")
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, (int, str)):
        dec = Decimal(str(value))
    elif isinstance(value, float):
        # Coerce via str to avoid surprise repr-rounding.
        dec = Decimal(str(value))
    else:
        raise TypeError(f"amount_str expected Decimal/int/str/float, got {type(value).__name__}")
    if quantize:
        dec = dec.quantize(_AMOUNT_QUANT)
    return f"{dec:f}"


class DecimalJSONEncoder(json.JSONEncoder):
    """JSON encoder that emits ``Decimal`` as numeric string.

    Use via ``json.dumps(payload, cls=DecimalJSONEncoder)``. The encoder
    emits decimals as JSON strings rather than Python floats, preserving
    exact precision through the wire boundary. Front-end consumers must
    parse with ``Number(value)`` (or string-display) as appropriate.

    >>> json.dumps({"amount": Decimal("123.4")}, cls=DecimalJSONEncoder)
    '{"amount": "123.40"}'
    """

    def default(self, obj: Any) -> Any:  # noqa: D401
        if isinstance(obj, Decimal):
            return amount_str(obj)
        return super().default(obj)


__all__ = ["amount_str", "DecimalJSONEncoder"]
