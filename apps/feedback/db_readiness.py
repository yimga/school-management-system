"""Detect whether feedback app tables exist (unmigrated production DBs)."""

from __future__ import annotations

from functools import lru_cache

from django.db import connection
from django.db.utils import ProgrammingError

_REQUIRED_TABLES = frozenset(
    {
        "feedback_featurerequest",
        "feedback_feedbacksubmission",
    }
)


@lru_cache(maxsize=1)
def feedback_schema_ready() -> bool:
    try:
        tables = set(connection.introspection.table_names())
    except Exception:
        return False
    return _REQUIRED_TABLES <= tables


def clear_feedback_schema_ready_cache() -> None:
    feedback_schema_ready.cache_clear()


def open_feature_request_count() -> int:
    if not feedback_schema_ready():
        return 0
    from apps.feedback.models import FeatureRequest

    # tenant-isolation-allow: manager-global-open-count-public-schema-help-center
    return FeatureRequest.objects.filter(
        status__in=[
            FeatureRequest.Status.SUBMITTED,
            FeatureRequest.Status.TRIAGING,
            FeatureRequest.Status.UNDER_REVIEW,
            FeatureRequest.Status.NEEDS_MORE_INFO,
        ]
    ).count()


def feature_request_queryset():
    from apps.feedback.models import FeatureRequest

    if not feedback_schema_ready():
        return FeatureRequest.objects.none()
    # tenant-isolation-allow: caller-scoped-queryset-factory-manager-and-feedback-views
    return FeatureRequest.objects.all()


def feedback_submission_queryset():
    from apps.feedback.models import FeedbackSubmission

    if not feedback_schema_ready():
        return FeedbackSubmission.objects.none()
    # tenant-isolation-allow: caller-scoped-queryset-factory-manager-and-feedback-views
    return FeedbackSubmission.objects.all()


def run_feedback_query(callable_fn, *, default):
    """Run a DB callable; return default when feedback tables are missing."""
    if not feedback_schema_ready():
        return default
    try:
        return callable_fn()
    except ProgrammingError:
        clear_feedback_schema_ready_cache()
        return default
