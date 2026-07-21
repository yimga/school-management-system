"""
Provider adapters for notifications (SMS, email, push, WhatsApp).
Internal contract only; no view or service imports vendor SDKs directly.
"""

from .sms_base import (
    SMS_PROVIDER_SDK_MODULES,
    SMSProvider,
    get_sms_provider,
    sms_sdk_available,
)
from .sms_twilio import TwilioSMSProvider
from .sms_africastalking import AfricasTalkingSMSProvider

__all__ = [
    "SMS_PROVIDER_SDK_MODULES",
    "SMSProvider",
    "get_sms_provider",
    "sms_sdk_available",
    "TwilioSMSProvider",
    "AfricasTalkingSMSProvider",
]
