"""Plan XVI: Feature-usage analytics — track_event(feature_code, school, user)."""

from apps.siteconfig.models import FeatureUsageEvent


def track_event(feature_code: str, school=None, user=None):
    """Record a feature-usage event for analytics. Call from views or APIs."""
    FeatureUsageEvent.objects.create(
        feature_code=feature_code,
        school=school,
        user=user,
    )
