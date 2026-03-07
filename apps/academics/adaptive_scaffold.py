"""
Plan XVII: Adaptive learning / gamification scaffold.
Learning paths, badges (reuse people.Badge), leaderboards — integration hooks for adaptive engines.
"""
from __future__ import annotations

# Reuse apps.people.models.Badge and BadgeType for badge awards.
# LearningPath: optional model in academics or siteconfig for sequenced content.
# LeaderboardEntry: optional model for points/rank per school or classroom.
# This module documents the scaffold; add models when implementing full adaptive flows.

def get_leaderboard(school, scope="school", limit=20):
    """
    Placeholder: return leaderboard entries (e.g. by points or badge count).
    scope: "school" | "classroom" | "subject"
    """
    return []


def award_badge_for_achievement(school, student, badge_type_code: str, reason: str = ""):
    """
    Integration hook: award a badge to a student (uses people.Badge).
    Call from achievement events or adaptive engine.
    """
    from apps.people.models import Badge, BadgeType
    bt = BadgeType.objects.filter(school=school, code=badge_type_code).first()
    if not bt:
        return None
    return Badge.objects.create(
        student=student,
        badge_type=bt,
        criteria_met={"reason": reason or badge_type_code},
    )
