"""
Phase 8 Task 7: Portal Services
Guardian linking, invitation management, communication
"""

from django.utils import timezone
from datetime import timedelta
import secrets


class GuardianLinkingService:
    """Manage parent-student linking"""

    INVITATION_VALIDITY_DAYS = 7

    @staticmethod
    def create_invitation(student_id, parent_email, created_by):
        """Create parent linking invitation"""
        from apps.portal.portal_models import GuardianLinkInvitation

        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(
            days=GuardianLinkingService.INVITATION_VALIDITY_DAYS
        )

        invitation = GuardianLinkInvitation(
            student_id=student_id,
            parent_email=parent_email,
            token=token,
            expires_at=expires_at,
            created_by=created_by,
        )
        invitation.save()

        return {
            "invitation_id": invitation.id,
            "token": token,
            "expires_at": expires_at.isoformat(),
            "status": "pending",
        }

    @staticmethod
    def accept_invitation(token, parent_id):
        """Accept linking invitation"""
        from apps.portal.portal_models import GuardianLinkInvitation, ParentStudentLink

        try:
            invitation = GuardianLinkInvitation.objects.get(token=token)

            if invitation.is_expired():
                return {"status": "expired", "error": "Invitation expired"}

            # Create link
            link, created = ParentStudentLink.objects.get_or_create(
                parent_id=parent_id,
                student_id=invitation.student_id,
                defaults={
                    "relationship": "parent",
                    "is_primary": True,
                    "access_level": "limited",
                    "linked_by": invitation.created_by,
                },
            )

            # Mark invitation as accepted
            invitation.status = "accepted"
            invitation.accepted_at = timezone.now()
            invitation.save()

            return {
                "status": "success",
                "link_id": link.id,
                "student_id": invitation.student_id,
            }

        except GuardianLinkInvitation.DoesNotExist:
            return {"status": "error", "error": "Invalid invitation"}

    @staticmethod
    def get_student_for_parent(parent_id):
        """Get all students linked to parent"""
        from apps.portal.portal_models import ParentStudentLink

        links = ParentStudentLink.objects.filter(parent_id=parent_id)

        students = []
        for link in links:
            students.append(
                {
                    "student_id": link.student_id,
                    "relationship": link.relationship,
                    "access_level": link.access_level,
                    "linked_at": link.linked_at.isoformat(),
                }
            )

        return students

    @staticmethod
    def update_access_level(parent_id, student_id, new_level):
        """Update parent access level"""
        from apps.portal.portal_models import ParentStudentLink

        try:
            link = ParentStudentLink.objects.get(
                parent_id=parent_id, student_id=student_id
            )
            link.access_level = new_level
            link.save()

            return {"status": "success", "new_level": new_level}

        except ParentStudentLink.DoesNotExist:
            return {"status": "error", "error": "Link not found"}


class NotificationService:
    """Send notifications to parents"""

    @staticmethod
    def create_notification(parent_id, student_id, notification_type, title, message):
        """Create notification for parent"""
        from apps.portal.portal_models import PortalNotification

        notification = PortalNotification(
            parent_id=parent_id,
            student_id=student_id,
            notification_type=notification_type,
            title=title,
            message=message,
        )
        notification.save()

        return {
            "notification_id": notification.id,
            "created_at": notification.created_at.isoformat(),
        }

    @staticmethod
    def send_grade_notification(student_id, grade_info):
        """Send grade update notification"""
        from apps.portal.portal_models import ParentStudentLink

        links = ParentStudentLink.objects.filter(student_id=student_id)
        notifications = []

        for link in links:
            title = f"New Grade: {grade_info.get('subject', 'Unknown')}"
            message = f"Score: {grade_info.get('score', 'N/A')}/100"

            notification = NotificationService.create_notification(
                link.parent_id, student_id, "grade", title, message
            )
            notifications.append(notification)

        return notifications

    @staticmethod
    def get_unread_notifications(parent_id):
        """Get unread notifications"""
        from apps.portal.portal_models import PortalNotification

        notifications = PortalNotification.objects.filter(
            parent_id=parent_id, is_read=False
        ).order_by("-created_at")

        result = []
        for notif in notifications:
            result.append(
                {
                    "id": notif.id,
                    "type": notif.notification_type,
                    "title": notif.title,
                    "message": notif.message,
                    "created_at": notif.created_at.isoformat(),
                }
            )

        return result


class PortalPreferencesService:
    """Manage parent portal preferences"""

    @staticmethod
    def get_preferences(parent_id):
        """Get parent preferences"""
        from apps.portal.portal_models import PortalPreferences

        try:
            prefs = PortalPreferences.objects.get(parent_id=parent_id)
            return {
                "language": prefs.language,
                "theme": prefs.theme,
                "notification_email": prefs.notification_email,
                "notification_sms": prefs.notification_sms,
                "show_grades": prefs.show_grades,
                "show_attendance": prefs.show_attendance,
                "show_fees": prefs.show_fees,
            }
        except PortalPreferences.DoesNotExist:
            return None

    @staticmethod
    def update_preferences(parent_id, preferences_dict):
        """Update preferences"""
        from django.contrib.auth import get_user_model
        from apps.portal.portal_models import PortalPreferences

        User = get_user_model()
        parent = User.objects.get(pk=parent_id)
        prefs, created = PortalPreferences.objects.get_or_create(parent_id=parent)

        for key, value in preferences_dict.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)

        prefs.save()

        return {"status": "updated", "preferences": preferences_dict}


class PortalAccessControlService:
    """Control portal feature access"""

    DEFAULT_FEATURES = [
        "view_grades",
        "view_attendance",
        "view_fees",
        "download_reports",
        "message_teacher",
    ]

    @staticmethod
    def initialize_access(parent_id):
        """Initialize default access for parent"""
        from apps.portal.portal_models import PortalFeatureAccess

        created_features = []

        for feature in PortalAccessControlService.DEFAULT_FEATURES:
            access, created = PortalFeatureAccess.objects.get_or_create(
                parent_id=parent_id, feature=feature, defaults={"is_enabled": True}
            )
            if created:
                created_features.append(feature)

        return created_features

    @staticmethod
    def can_access_feature(parent_id, feature):
        """Check if parent can access feature"""
        from apps.portal.portal_models import PortalFeatureAccess

        try:
            access = PortalFeatureAccess.objects.get(
                parent_id=parent_id, feature=feature
            )
            return access.is_enabled
        except PortalFeatureAccess.DoesNotExist:
            return False

    @staticmethod
    def revoke_feature(parent_id, feature):
        """Revoke feature access"""
        from apps.portal.portal_models import PortalFeatureAccess

        try:
            access = PortalFeatureAccess.objects.get(
                parent_id=parent_id, feature=feature
            )
            access.is_enabled = False
            access.save()
            return {"status": "revoked"}
        except PortalFeatureAccess.DoesNotExist:
            return {"status": "error", "error": "Feature access not found"}


class PortalMessagingService:
    """Handle parent-school messaging"""

    @staticmethod
    def send_message(sender_id, recipient_id, subject, message):
        """Send message"""
        from apps.portal.portal_models import ParentMessage

        msg = ParentMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            subject=subject,
            message=message,
        )
        msg.save()

        return {
            "message_id": msg.id,
            "status": "sent",
            "created_at": msg.created_at.isoformat(),
        }

    @staticmethod
    def get_inbox(user_id):
        """Get messages for user"""
        from apps.portal.portal_models import ParentMessage

        messages = (
            ParentMessage.objects.filter(recipient_id=user_id)
            .exclude(status="archived")
            .order_by("-created_at")
        )

        result = []
        for msg in messages:
            result.append(
                {
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "subject": msg.subject,
                    "preview": msg.message[:100],
                    "is_read": msg.status == "read",
                    "created_at": msg.created_at.isoformat(),
                }
            )

        return result

    @staticmethod
    def reply_to_message(original_id, sender_id, recipient_id, message_text):
        """Reply to message"""
        from apps.portal.portal_models import ParentMessage

        original = ParentMessage.objects.get(id=original_id)

        reply = ParentMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            subject=f"RE: {original.subject}",
            message=message_text,
            reply_to=original,
        )
        reply.save()

        return {
            "message_id": reply.id,
            "status": "sent",
        }


class PortalSecurityService:
    """Handle portal security and audit logging"""

    SESSION_TIMEOUT_MINUTES = 30

    @staticmethod
    def create_session(parent_id, ip_address, user_agent, device_type="web"):
        """Create portal session"""
        from apps.portal.portal_models import PortalSession

        token = secrets.token_urlsafe(32)

        session = PortalSession(
            parent_id=parent_id,
            session_token=token,
            ip_address=ip_address,
            user_agent=user_agent,
            device_type=device_type,
        )
        session.save()

        return {
            "session_token": token,
            "created_at": session.login_at.isoformat(),
        }

    @staticmethod
    def log_action(
        parent_id, action, description, ip_address, user_agent, details=None
    ):
        """Log portal action"""
        from apps.portal.portal_models import PortalAuditLog

        if details is None:
            details = {}

        log = PortalAuditLog(
            parent_id=parent_id,
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )
        log.save()

        return {"log_id": log.id}

    @staticmethod
    def get_audit_log(parent_id, days=30):
        """Get audit log for parent"""
        from apps.portal.portal_models import PortalAuditLog
        from datetime import timedelta

        start_date = timezone.now() - timedelta(days=days)

        logs = PortalAuditLog.objects.filter(
            parent_id=parent_id, timestamp__gte=start_date
        ).order_by("-timestamp")

        result = []
        for log in logs:
            result.append(
                {
                    "action": log.action,
                    "description": log.description,
                    "timestamp": log.timestamp.isoformat(),
                    "ip_address": log.ip_address,
                }
            )

        return result
