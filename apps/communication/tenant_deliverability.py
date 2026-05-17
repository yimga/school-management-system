"""Per-tenant email deliverability aggregator.

12-pillar audit P11 follow-up. The communication app sends mail
through the per-tenant Anymail backend (memory v2.79) and stores
delivery state. Without aggregation, operators have no visibility
into "is this tenant's mail reaching parents?" — a single bounce
incident can poison the school's communication channel for weeks.

This module computes per-tenant deliverability metrics over a
configurable window. Inputs are abstract iterables (so the same
helper can be exercised by tests with synthetic data + by the live
mailbox / webhook ingest store at runtime).

Metric definitions (industry standard):

  * delivered_rate = delivered / sent
  * bounce_rate    = bounced / sent           (target < 2%)
  * complaint_rate = complained / sent        (target < 0.1%)
  * unsubscribe_rate = unsubscribed / sent    (advisory only)
  * suppression_size = currently-suppressed recipients

Health bands match SendGrid / Mailgun reporting:
  * "healthy"      bounce < 2% AND complaint < 0.1%
  * "warning"      bounce < 5% AND complaint < 0.3%
  * "critical"     otherwise — the tenant should pause the channel.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

BOUNCE_HEALTHY = 0.02
BOUNCE_WARNING = 0.05
COMPLAINT_HEALTHY = 0.001
COMPLAINT_WARNING = 0.003


@dataclass(frozen=True)
class DeliverabilityEvent:
    """Single deliverability fact for one outbound message.

    Status values: "sent", "delivered", "bounced", "complained",
    "unsubscribed", "suppressed".
    """
    school_id: int
    status: str
    occurred_at: str  # ISO-8601 string (UTC); not parsed here.


@dataclass(frozen=True)
class DeliverabilityReport:
    school_id: int
    sent: int
    delivered: int
    bounced: int
    complained: int
    unsubscribed: int
    suppressed: int
    delivered_rate: float
    bounce_rate: float
    complaint_rate: float
    unsubscribe_rate: float
    health: str

    def as_dict(self) -> dict:
        return asdict(self)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _classify_health(bounce_rate: float, complaint_rate: float) -> str:
    if bounce_rate < BOUNCE_HEALTHY and complaint_rate < COMPLAINT_HEALTHY:
        return "healthy"
    if bounce_rate < BOUNCE_WARNING and complaint_rate < COMPLAINT_WARNING:
        return "warning"
    return "critical"


def aggregate(events: Iterable[DeliverabilityEvent]) -> list[DeliverabilityReport]:
    """Group events by school and compute a :class:`DeliverabilityReport`."""
    buckets: dict[int, dict[str, int]] = {}
    for ev in events:
        b = buckets.setdefault(
            ev.school_id,
            {"sent": 0, "delivered": 0, "bounced": 0, "complained": 0,
             "unsubscribed": 0, "suppressed": 0},
        )
        if ev.status in b:
            b[ev.status] += 1
    reports: list[DeliverabilityReport] = []
    for school_id, counts in buckets.items():
        sent = max(counts["sent"], counts["delivered"] + counts["bounced"])
        delivered_rate = _safe_ratio(counts["delivered"], sent)
        bounce_rate = _safe_ratio(counts["bounced"], sent)
        complaint_rate = _safe_ratio(counts["complained"], sent)
        unsubscribe_rate = _safe_ratio(counts["unsubscribed"], sent)
        reports.append(DeliverabilityReport(
            school_id=school_id,
            sent=sent,
            delivered=counts["delivered"],
            bounced=counts["bounced"],
            complained=counts["complained"],
            unsubscribed=counts["unsubscribed"],
            suppressed=counts["suppressed"],
            delivered_rate=round(delivered_rate, 4),
            bounce_rate=round(bounce_rate, 4),
            complaint_rate=round(complaint_rate, 4),
            unsubscribe_rate=round(unsubscribe_rate, 4),
            health=_classify_health(bounce_rate, complaint_rate),
        ))
    reports.sort(key=lambda r: r.school_id)
    return reports


__all__ = [
    "DeliverabilityEvent",
    "DeliverabilityReport",
    "aggregate",
    "BOUNCE_HEALTHY",
    "BOUNCE_WARNING",
    "COMPLAINT_HEALTHY",
    "COMPLAINT_WARNING",
]
