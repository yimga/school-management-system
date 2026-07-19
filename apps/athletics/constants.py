"""Athletics module constants — single home for every magic number/label.

Keeping literals here (not inline in models/services) satisfies
``scripts/scan_magic_numbers.py`` (which exempts a module named ``constants``)
and gives operators one place to tune eligibility thresholds and squad sizes.
"""

from __future__ import annotations

from decimal import Decimal

# ── Squad / roster ─────────────────────────────────────────────────────────
DEFAULT_SQUAD_SIZE = 15
DEFAULT_ROSTER_CAP = 30
DEFAULT_CLUB_CAPACITY = 40

# ── Eligibility thresholds ─────────────────────────────────────────────────
# An athlete is academically eligible at or above this average (percent scale)
# and attendance-eligible at or above this attendance rate (percent).
MIN_ELIGIBILITY_AVERAGE = Decimal("50.0")
MIN_ELIGIBILITY_ATTENDANCE_PCT = Decimal("75.0")
# Window (days) of attendance history the eligibility check samples.
ELIGIBILITY_ATTENDANCE_WINDOW_DAYS = 90

# ── Consent ────────────────────────────────────────────────────────────────
PARTICIPATION_CONSENT_EXPIRY_DAYS = 30
CONSENT_TEXT_VERSION = "v1"

# ── Medical clearance ──────────────────────────────────────────────────────
# Default validity window (days) a recorded fitness-to-play clearance stays
# "current" for. A physical is not indefinite; after this the clearance falls
# out of the eligibility resolver's ``valid_until >= today`` window and the
# athlete must be re-cleared. Roughly one school year. FLAGGED product default —
# a school may want a shorter cadence (e.g. per-season).
MEDICAL_CLEARANCE_VALIDITY_DAYS = 365

# ── Fields / limits ────────────────────────────────────────────────────────
MEDICAL_CLEARANCE_MAX_UPLOAD_MB = 5

# ── Display limits (HTTP layer) ────────────────────────────────────────────
# Cap the school-wide fixture calendar and the family fixture list so a large
# season never renders an unbounded table.
ADMIN_FIXTURE_LIST_LIMIT = 200
FAMILY_FIXTURE_LIST_LIMIT = 50
