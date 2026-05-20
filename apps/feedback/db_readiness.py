"""Detect whether feedback app tables exist (unmigrated production DBs)."""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

from django.db import connection
from django.db.utils import ProgrammingError

_REQUIRED_TABLES = frozenset(
    {
        "feedback_featurerequest",
        "feedback_feedbacksubmission",
        "feedback_releasenote",
        "feedback_roadmapitem",
        "feedback_surveyresponse",
    }
)

_DEBUG_LOG = Path(__file__).resolve().parents[2] / "debug-22cfee.log"


# region agent log
def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    try:
        payload = {
            "sessionId": "22cfee",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except OSError:
        pass


# endregion


@lru_cache(maxsize=1)
def feedback_schema_ready() -> bool:
    try:
        tables = set(connection.introspection.table_names())
    except Exception:
        # region agent log
        _agent_debug_log("H-B", "db_readiness.feedback_schema_ready", "table_names_failed", {})
        # endregion
        return False
    missing = sorted(_REQUIRED_TABLES - tables)
    ready = not missing
    # region agent log
    _agent_debug_log(
        "H-B",
        "db_readiness.feedback_schema_ready",
        "schema_check",
        {"ready": ready, "missing": missing[:8], "missing_count": len(missing)},
    )
    # endregion
    return ready


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


def roadmap_queryset():
    from apps.feedback.models import RoadmapItem

    if not feedback_schema_ready():
        return RoadmapItem.objects.none()
    # tenant-isolation-allow: caller-scoped-queryset-factory-manager-and-feedback-views
    return RoadmapItem.objects.all()


def run_feedback_query(callable_fn, *, default):
    """Run a DB callable; return default when feedback tables are missing."""
    if not feedback_schema_ready():
        return default
    try:
        return callable_fn()
    except ProgrammingError:
        clear_feedback_schema_ready_cache()
        return default
