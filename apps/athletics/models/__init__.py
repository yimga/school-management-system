"""Athletics models package — re-exports so ``get_model('athletics', X)`` works."""

from .booking import FixtureVenueBooking
from .catalog import Season, Sport, TeamKitFee
from .consent import (
    ParticipationConsent,
    ParticipationConsentDecision,
    ParticipationConsentError,
)
from .eligibility import EligibilityRecord
from .fixtures import Fixture, FixtureResult, FixtureTravel
from .roster import MedicalClearance, TeamMembership
from .team import CoachAssignment, Team

__all__ = [
    "Sport",
    "Season",
    "TeamKitFee",
    "Team",
    "CoachAssignment",
    "TeamMembership",
    "MedicalClearance",
    "ParticipationConsent",
    "ParticipationConsentDecision",
    "ParticipationConsentError",
    "EligibilityRecord",
    "Fixture",
    "FixtureResult",
    "FixtureTravel",
    "FixtureVenueBooking",
]
