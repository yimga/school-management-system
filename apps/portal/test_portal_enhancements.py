"""
Phase 8 Task 7: Portal Tests
Guardian linking, notifications, messaging tests
"""

from django.test import TestCase


class GuardianLinkingServiceTestCase(TestCase):
    """Test guardian linking service"""
    
    def test_create_invitation(self):
        """Test creating invitation"""
        from apps.portal.portal_services import GuardianLinkingService
        
        result = GuardianLinkingService.create_invitation(
            student_id=1,
            parent_email='parent@example.com',
            created_by=2
        )
        
        self.assertEqual(result['status'], 'pending')
        self.assertIn('token', result)
        self.assertIn('invitation_id', result)
    
    def test_accept_invitation(self):
        """Test accepting invitation"""
        from apps.portal.portal_services import GuardianLinkingService
        
        # Create invitation
        result = GuardianLinkingService.create_invitation(
            student_id=1,
            parent_email='parent@example.com',
            created_by=2
        )
        
        token = result['token']
        
        # Accept invitation
        accept_result = GuardianLinkingService.accept_invitation(
            token=token,
            parent_id=3
        )
        
        self.assertEqual(accept_result['status'], 'success')
        self.assertEqual(accept_result['student_id'], 1)


class NotificationServiceTestCase(TestCase):
    """Test notification service"""
    
    def test_create_notification(self):
        """Test creating notification"""
        from apps.portal.portal_services import NotificationService
        
        result = NotificationService.create_notification(
            parent_id=1,
            student_id=2,
            notification_type='grade',
            title='New Grade',
            message='Score: 85/100'
        )
        
        self.assertIn('notification_id', result)
        self.assertIn('created_at', result)
    
    def test_get_unread_notifications(self):
        """Test getting unread notifications"""
        from apps.portal.portal_services import NotificationService
        
        # Create notification
        NotificationService.create_notification(
            parent_id=1,
            student_id=2,
            notification_type='grade',
            title='New Grade',
            message='Score: 85/100'
        )
        
        # Get unread
        notifications = NotificationService.get_unread_notifications(parent_id=1)
        
        self.assertGreater(len(notifications), 0)
        self.assertEqual(notifications[0]['title'], 'New Grade')


class PortalPreferencesServiceTestCase(TestCase):
    """Test preferences service"""
    
    def test_update_preferences(self):
        """Test updating preferences"""
        from django.contrib.auth import get_user_model
        from apps.portal.portal_services import PortalPreferencesService
        
        User = get_user_model()
        user = User.objects.create_user(
            username='portal_prefs_%s' % id(self), email='prefs@test.com', password='pass'
        )
        prefs_dict = {
            'language': 'fr',
            'theme': 'dark',
            'notification_email': False,
        }
        
        result = PortalPreferencesService.update_preferences(user.id, prefs_dict)
        
        self.assertEqual(result['status'], 'updated')


class PortalAccessControlTestCase(TestCase):
    """Test access control"""
    
    def test_initialize_access(self):
        """Test initializing access"""
        from apps.portal.portal_services import PortalAccessControlService
        
        features = PortalAccessControlService.initialize_access(parent_id=1)
        
        self.assertGreater(len(features), 0)
    
    def test_can_access_feature(self):
        """Test feature access check"""
        from apps.portal.portal_services import PortalAccessControlService
        
        # Initialize
        PortalAccessControlService.initialize_access(parent_id=1)
        
        # Check access
        can_access = PortalAccessControlService.can_access_feature(1, 'view_grades')
        
        self.assertTrue(can_access)


class PortalMessagingServiceTestCase(TestCase):
    """Test messaging service"""
    
    def test_send_message(self):
        """Test sending message"""
        from apps.portal.portal_services import PortalMessagingService
        
        result = PortalMessagingService.send_message(
            sender_id=1,
            recipient_id=2,
            subject='Test Message',
            message='This is a test'
        )
        
        self.assertEqual(result['status'], 'sent')
        self.assertIn('message_id', result)
    
    def test_get_inbox(self):
        """Test getting inbox"""
        from apps.portal.portal_services import PortalMessagingService
        
        # Send message
        PortalMessagingService.send_message(
            sender_id=1,
            recipient_id=2,
            subject='Test Message',
            message='This is a test'
        )
        
        # Get inbox
        messages = PortalMessagingService.get_inbox(user_id=2)
        
        self.assertGreater(len(messages), 0)


class PortalSecurityServiceTestCase(TestCase):
    """Test security service"""
    
    def test_create_session(self):
        """Test creating session"""
        from apps.portal.portal_services import PortalSecurityService
        
        result = PortalSecurityService.create_session(
            parent_id=1,
            ip_address='192.168.1.1',
            user_agent='Mozilla/5.0',
        )
        
        self.assertIn('session_token', result)
    
    def test_log_action(self):
        """Test logging action"""
        from apps.portal.portal_services import PortalSecurityService
        
        result = PortalSecurityService.log_action(
            parent_id=1,
            action='login',
            description='Parent login',
            ip_address='192.168.1.1',
            user_agent='Mozilla/5.0'
        )
        
        self.assertIn('log_id', result)
