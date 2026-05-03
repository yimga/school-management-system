"""Operator console routes (domain outbox + platform log). Namespace ``events``."""

from django.urls import path

from . import views_console, views_event_ops

app_name = "events"

urlpatterns = [
    path("", views_console.event_console, name="event_console"),
    path(
        "analytics/",
        views_event_ops.event_analytics_console,
        name="event_analytics_console",
    ),
    path(
        "dlq/",
        views_event_ops.event_dlq_console,
        name="event_dlq_console",
    ),
    path(
        "domain/<uuid:event_id>/",
        views_console.event_domain_detail,
        name="event_domain_detail",
    ),
    path(
        "platform/<int:event_pk>/",
        views_console.event_platform_detail,
        name="event_platform_detail",
    ),
    path("replay/", views_console.event_replay, name="event_replay"),
]
