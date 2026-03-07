# Follow-up: paste this block into apps/dashboard/context.py after
#     ]
#
# and before
#     perms = {
#
# Then commit: "Ops watch: add Signatures, Contact Requests, Messages, Announcements"

    # Ops watch extras: Pending Signatures, Contact Requests, Unread Messages, Announcements
    staff_like = bool(
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or role_code in (admin_roles | {"SECRETARY", "BURSAR", "ACCOUNTANT", "PROPRIETOR", "DISCIPLINE_MASTER"})
    )
    pending_signatures = 0
    if can_manage_settings or staff_like:
        try:
            from apps.portal.models import FormSignature
            pending_signatures = FormSignature.objects.filter(status=FormSignature.SignatureStatus.PENDING).count()
        except Exception:
            pass
    if pending_signatures > 0:
        operations_watch.append({
            "key": "pending_signatures",
            "label": "Pending Signatures",
            "value": pending_signatures,
            "status": _status_from_value(pending_signatures, warn_at=1, danger_at=5),
            "url": _safe_reverse("portal:signature_requests_manage"),
            "icon": "bi-pen",
        })

    contact_requests_count = 0
    if staff_like:
        try:
            from apps.communication.models import ContactRequest
            contact_requests_count = ContactRequest.objects.exclude(
                status__in=(ContactRequest.Status.RESOLVED, ContactRequest.Status.CLOSED)
            ).count()
        except Exception:
            pass
    if contact_requests_count > 0:
        operations_watch.append({
            "key": "contact_requests",
            "label": "Contact Requests",
            "value": contact_requests_count,
            "status": _status_from_value(contact_requests_count, warn_at=1, danger_at=5),
            "url": _safe_reverse("portal:staff_contact_request_list"),
            "icon": "bi-inbox",
        })

    messages_unread = _safe_int(getattr(request, "messages_unread_count", None))
    try:
        from apps.communication.models import Message
        if messages_unread == 0 and user:
            messages_unread = Message.objects.filter(recipient=user, is_read=False).count()
    except Exception:
        pass
    if messages_unread > 0:
        operations_watch.append({
            "key": "unread_messages",
            "label": "Unread Messages",
            "value": messages_unread,
            "status": _status_from_value(messages_unread, warn_at=1, danger_at=10),
            "url": _safe_reverse("accounts:user_messages"),
            "icon": "bi-chat-dots",
        })

    announcements_pending = 0
    if can_use_messages:
        try:
            from apps.communication.models import Announcement
            announcements_pending = Announcement.objects.filter(
                status=Announcement.Status.PENDING_APPROVAL
            ).count()
        except Exception:
            pass
    if announcements_pending > 0:
        operations_watch.append({
            "key": "announcements_pending",
            "label": "Announcements (pending)",
            "value": announcements_pending,
            "status": "warn",
            "url": _safe_reverse("communication:announcement_list_pending") or _safe_reverse("communication:announcement_create"),
            "icon": "bi-megaphone",
        })
