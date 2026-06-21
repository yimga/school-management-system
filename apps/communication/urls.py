"""
URL patterns for communication app.
"""

from django.urls import path
from . import views_groups, views_announcements, views_narrative
from . import views_whatsapp_webhook
from . import views_sms_inbound_webhook
from . import views_preferences

app_name = "communication"

urlpatterns = [
    # Wave H (v3.95.0): WhatsApp Parent OS — Meta Business webhook.
    path(  # rbac-allow: intentionally-public-meta-webhook-hmac-signature-verified-via-verify_webhook
        "whatsapp/webhook/",
        views_whatsapp_webhook.whatsapp_webhook,
        name="whatsapp_webhook",
    ),
    # Inbound SMS keyword handling (STOP/HELP/START) — consent opt-out source.
    path(  # rbac-allow: intentionally-public-sms-webhook-twilio-signature-verified-in-view
        "sms/inbound/",
        views_sms_inbound_webhook.sms_inbound_webhook,
        name="sms_inbound_webhook",
    ),
    # Twilio delivery status callbacks → MessageDeliveryReceipt.
    path(  # rbac-allow: intentionally-public-sms-status-webhook-twilio-signature-verified-in-view
        "sms/status/",
        views_sms_inbound_webhook.sms_status_webhook,
        name="sms_status_webhook",
    ),
    # Consent preference centre (logged-in user manages their own email consent).
    path(
        "preferences/consent/",
        views_preferences.consent_preferences,
        name="consent_preferences",
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
    # IM-5: live new-message delivery for an open group thread (poll endpoint).
    path(
        "groups/<int:thread_id>/messages-since/",
        views_groups.group_messages_since,
        name="group_messages_since",
    ),
    # IM-5: group message attachment download (membership-gated).
    path(
        "groups/attachment/<int:attachment_id>/",
        views_groups.group_attachment_download,
        name="group_attachment_download",
    ),
    # IM-6: edit / soft-delete a group message.
    path(
        "groups/<int:thread_id>/message/<int:message_id>/edit/",
        views_groups.group_message_edit,
        name="group_message_edit",
    ),
    path(
        "groups/<int:thread_id>/message/<int:message_id>/delete/",
        views_groups.group_message_delete,
        name="group_message_delete",
    ),
    # IM-7: mute/unmute a group thread + cache-backed typing indicator.
    path(
        "groups/<int:thread_id>/mute/",
        views_groups.group_mute_toggle,
        name="group_mute_toggle",
    ),
    path(
        "groups/<int:thread_id>/typing/",
        views_groups.group_typing,
        name="group_typing",
    ),
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
