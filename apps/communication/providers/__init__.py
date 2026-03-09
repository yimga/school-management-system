"""
Provider adapters for notifications (SMS, email, push, WhatsApp).
Internal contract only; no view or service imports vendor SDKs directly.
"""
from .sms_base import SMSProvider, get_sms_provider
from .sms_twilio import TwilioSMSProvider
from .sms_africastalking import AfricasTalkingSMSProvider

__all__ = [
    "SMSProvider",
    "get_sms_provider",
    "TwilioSMSProvider",
    "AfricasTalkingSMSProvider",
]
