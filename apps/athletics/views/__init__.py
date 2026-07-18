"""Athletics HTTP views package.

Re-exports every view callable so ``apps.athletics.urls`` (and any ``get_model``-free
introspection) can reach them from ``apps.athletics.views`` directly.
"""

from apps.athletics.views.admin_console import admin_fixtures, admin_seasons
from apps.athletics.views.coach import (
    coach_add_member,
    coach_cancel_fixture,
    coach_dashboard,
    coach_eligibility,
    coach_fixtures,
    coach_record_clearance,
    coach_record_result,
    coach_request_consent,
    coach_schedule_fixture,
    coach_team_detail,
)
from apps.athletics.views.consent_public import (
    participation_consent_decide,
    participation_consent_public,
)
from apps.athletics.views.family import family_my_team

__all__ = [
    "admin_fixtures",
    "admin_seasons",
    "coach_add_member",
    "coach_cancel_fixture",
    "coach_dashboard",
    "coach_eligibility",
    "coach_fixtures",
    "coach_record_clearance",
    "coach_record_result",
    "coach_request_consent",
    "coach_schedule_fixture",
    "coach_team_detail",
    "family_my_team",
    "participation_consent_decide",
    "participation_consent_public",
]
