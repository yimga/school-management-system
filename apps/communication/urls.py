"""
URL patterns for communication app.
"""

from django.urls import path
from . import views_groups, views_announcements, views_narrative
from . import views_whatsapp_webhook

app_name = "communication"

urlpatterns = [
    # Wave H (v3.95.0): WhatsApp Parent OS — Meta Business webhook.
    path(  # rbac-allow: intentionally-public-meta-webhook-hmac-signature-verified-via-verify_webhook
        "whatsapp/webhook/",
        views_whatsapp_webhook.whatsapp_webhook,
        name="whatsapp_webhook",
    ),
    # Groups/Threads
    path("groups/", views_groups.group_list, name="group_list"),
    path("groups/create/", views_groups.group_create, name="group_create"),
    path("groups/<int:thread_id>/", views_groups.group_detail, name="group_detail"),
    path(
        "groups/<int:thread_id>/manage/", views_groups.group_manage, name="group_manage"
    ),
    path("groups/<int:thread_id>/join/", views_groups.group_join, name="group_join"),
    path("groups/<int:thread_id>/leave/", views_groups.group_leave, name="group_leave"),
    # Announcements
    path(
        "announcements/create/",
        views_announcements.announcement_create,
        name="announcement_create",
    ),
    path(
        "announcements/class/",
        views_announcements.class_announcement_create,
        name="class_announcement_create",
    ),
    path(
        "announcements/pending/",
        views_announcements.announcement_list_pending,
        name="announcement_list_pending",
    ),
    path(
        "announcements/<int:announcement_id>/",
        views_announcements.announcement_detail,
        name="announcement_detail",
    ),
    path(
        "announcements/<int:announcement_id>/edit/",
        views_announcements.announcement_edit,
        name="announcement_edit",
    ),
    path(
        "announcements/<int:announcement_id>/approve/",
        views_announcements.announcement_approve,
        name="announcement_approve",
    ),
    path(
        "announcements/department/",
        views_announcements.department_announcement_create,
        name="department_announcement_create",
    ),
    # AI narrative feedback (teacher-approved parent message)
    path("narratives/", views_narrative.narrative_list, name="narrative_list"),
    path(
        "narratives/<int:narrative_id>/approve/",
        views_narrative.narrative_approve,
        name="narrative_approve",
    ),
]
