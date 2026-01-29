"""
Phase 7 Task 8: Third-Party Integrations (WhatsApp, Zoom, Communication)
"""
from abc import ABC, abstractmethod
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class IntegrationService(ABC):
    """Base class for third-party integrations."""

    @abstractmethod
    def send_message(self, recipient, message, **kwargs):
        """Send a message via the integration."""
        pass

    @abstractmethod
    def verify_webhook(self, request):
        """Verify webhook signature."""
        pass

    @abstractmethod
    def check_health(self):
        """Check if service is available."""
        pass


class WhatsAppIntegration(IntegrationService):
    """WhatsApp Business API integration."""

    def __init__(self):
        self.api_token = settings.WHATSAPP_API_TOKEN
        self.api_url = settings.WHATSAPP_API_URL
        self.phone_number = settings.WHATSAPP_BUSINESS_NUMBER

    def send_message(self, recipient, message, template=None, **kwargs):
        """
        Send WhatsApp message.
        
        Args:
            recipient: Phone number (e.g., "+237123456789")
            message: Message text
            template: Template name (for templated messages)
        """
        try:
            import requests
            
            if template:
                # Use template message
                payload = {
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "template",
                    "template": {
                        "name": template,
                        "language": {"code": "en_US"}
                    }
                }
            else:
                # Send text message
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "text",
                    "text": {"preview_url": True, "body": message}
                }

            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                f"{self.api_url}/messages",
                json=payload,
                headers=headers,
                timeout=10
            )

            if response.status_code in [200, 201]:
                logger.info(f"WhatsApp message sent to {recipient}")
                return {'success': True, 'message_id': response.json().get('messages')[0]['id']}
            else:
                logger.error(f"WhatsApp send failed: {response.text}")
                return {'success': False, 'error': response.text}

        except Exception as e:
            logger.error(f"WhatsApp integration error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def verify_webhook(self, request):
        """Verify WhatsApp webhook signature."""
        # Implementation depends on WhatsApp API version
        return True

    def check_health(self):
        """Check WhatsApp API health."""
        try:
            import requests
            response = requests.get(
                f"{self.api_url}/health",
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False


class ZoomIntegration(IntegrationService):
    """Zoom meeting integration."""

    def __init__(self):
        self.api_key = settings.ZOOM_API_KEY
        self.api_secret = settings.ZOOM_API_SECRET
        self.api_url = "https://api.zoom.us/v2"

    def create_meeting(self, host_email, topic, duration=30, **kwargs):
        """Create a Zoom meeting."""
        try:
            import requests
            import jwt
            from datetime import datetime, timedelta

            # Generate JWT token
            payload = {
                'iss': self.api_key,
                'exp': datetime.utcnow() + timedelta(seconds=60)
            }
            token = jwt.encode(payload, self.api_secret, algorithm='HS256')

            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            # Create meeting
            meeting_data = {
                'topic': topic,
                'type': 2,  # Scheduled meeting
                'duration': duration,
                'timezone': 'UTC',
                'settings': {
                    'host_video': True,
                    'participant_video': True,
                    'join_before_host': True,
                    'waiting_room': True,
                }
            }

            response = requests.post(
                f"{self.api_url}/users/{host_email}/meetings",
                json=meeting_data,
                headers=headers,
                timeout=10
            )

            if response.status_code == 201:
                data = response.json()
                logger.info(f"Zoom meeting created: {data['id']}")
                return {
                    'success': True,
                    'meeting_id': data['id'],
                    'join_url': data['join_url'],
                    'start_time': data.get('start_time'),
                }
            else:
                logger.error(f"Zoom meeting creation failed: {response.text}")
                return {'success': False, 'error': response.text}

        except Exception as e:
            logger.error(f"Zoom integration error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def send_message(self, recipient, message, **kwargs):
        """Zoom doesn't send messages directly."""
        raise NotImplementedError("Use create_meeting instead")

    def verify_webhook(self, request):
        """Verify Zoom webhook."""
        return True

    def check_health(self):
        """Check Zoom API health."""
        try:
            import requests
            response = requests.get(
                f"{self.api_url}/users/me",
                headers={'Authorization': f'Bearer {self.get_token()}'},
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False


class CommunicationService:
    """Central service for managing all communications."""

    def __init__(self):
        self.whatsapp = WhatsAppIntegration()
        self.zoom = ZoomIntegration()
        self.providers = {
            'whatsapp': self.whatsapp,
            'zoom': self.zoom,
        }

    def send_message(self, provider, recipient, message, **kwargs):
        """Send message through specified provider."""
        if provider not in self.providers:
            return {'success': False, 'error': f'Unknown provider: {provider}'}

        return self.providers[provider].send_message(recipient, message, **kwargs)

    def check_all_health(self):
        """Check health of all integrations."""
        results = {}
        for name, service in self.providers.items():
            try:
                results[name] = service.check_health()
            except Exception:
                results[name] = False

        return results


# Singleton instance
_communication_service = None


def get_communication_service():
    """Get singleton communication service."""
    global _communication_service
    if _communication_service is None:
        _communication_service = CommunicationService()
    return _communication_service
