"""
Conversion: URLs whose POSTs count as a substantive first value action.

Used by GrowthFunnelMiddleware to align funnel first_action + activation gate clearing
with marks / attendance / reports / payments — not generic settings saves.
"""

from __future__ import annotations

# Lowercase path fragments (tenant-relative paths).
_SUBSTANTIVE_POST_FRAGMENTS: tuple[str, ...] = (
    # Attendance
    "attendance",
    "attend",
    "take_student_attendance",
    "period_roll",
    # Marks / grading
    "marks",
    "gradebook",
    "grading",
    "evals",
    "assessment",
    # Reports
    "report",
    "reports/",
    "publish_term",
    # Payments / fees / billing touches
    "payment",
    "invoice",
    "fee",
    "checkout",
    "billing",
    "finance",
    "stripe",
    "wallet",
)


def path_indicates_substantive_conversion_post(path: str) -> bool:
    """Return True when URL path suggests marks/attendance/report/payment-class POST."""
    p = (path or "").lower().replace("\\", "/")
    return any(frag in p for frag in _SUBSTANTIVE_POST_FRAGMENTS)
