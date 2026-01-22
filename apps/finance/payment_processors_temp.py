"""Payment Gateway Processors"""
from abc import ABC, abstractmethod
from decimal import Decimal
import hashlib
import hmac


class PaymentProcessor(ABC):
    """Base payment processor interface."""
    
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
    
    @abstractmethod
    def charge(self, amount, currency, reference, metadata):
        """Process a charge."""
        pass
    
    @abstractmethod
    def refund(self, transaction_id, amount, reason):
        """Process a refund."""
        pass
    
    @abstractmethod
    def verify_webhook(self, payload, signature):
        """Verify webhook signature."""
        pass


class StripeProcessor(PaymentProcessor):
    """Stripe payment gateway processor."""
    
    def charge(self, amount, currency, reference, metadata):
        """Process Stripe charge."""
        # Mock implementation for phase
        return {
            'status': 'success',
            'transaction_id': f'stripe_{reference}',
            'amount': str(amount),
            'currency': currency,
            'timestamp': __import__('datetime').datetime.now().isoformat()
        }
    
    def refund(self, transaction_id, amount, reason):
        """Process Stripe refund."""
        return {
            'status': 'success',
            'refund_id': f'refund_{transaction_id}',
            'amount': str(amount),
            'reason': reason
        }
    
    def verify_webhook(self, payload, signature):
        """Verify Stripe webhook."""
        expected_sig = hmac.new(
            self.api_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, signature)


class PayPalProcessor(PaymentProcessor):
    """PayPal payment gateway processor."""
    
    def charge(self, amount, currency, reference, metadata):
        """Process PayPal charge."""
        return {
            'status': 'success',
            'transaction_id': f'paypal_{reference}',
            'amount': str(amount),
            'currency': currency,
            'payer_email': metadata.get('payer_email', ''),
            'timestamp': __import__('datetime').datetime.now().isoformat()
        }
    
    def refund(self, transaction_id, amount, reason):
        """Process PayPal refund."""
        return {
            'status': 'success',
            'refund_id': f'refund_{transaction_id}',
            'amount': str(amount),
            'reason': reason
        }
    
    def verify_webhook(self, payload, signature):
        """Verify PayPal webhook."""
        expected_sig = hmac.new(
            self.api_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, signature)


class FlutterwaveProcessor(PaymentProcessor):
    """Flutterwave payment gateway processor."""
    
    def charge(self, amount, currency, reference, metadata):
        """Process Flutterwave charge."""
        return {
            'status': 'success',
            'transaction_id': f'flutterwave_{reference}',
            'amount': str(amount),
            'currency': currency,
            'timestamp': __import__('datetime').datetime.now().isoformat()
        }
    
    def refund(self, transaction_id, amount, reason):
        """Process Flutterwave refund."""
        return {
            'status': 'success',
            'refund_id': f'refund_{transaction_id}',
            'amount': str(amount)
        }
    
    def verify_webhook(self, payload, signature):
        """Verify Flutterwave webhook."""
        expected_sig = hashlib.sha256(
            (payload + self.api_secret).encode()
        ).hexdigest()
        return hmac.compare_digest(expected_sig, signature)


class PaystackProcessor(PaymentProcessor):
    """Paystack payment gateway processor."""
    
    def charge(self, amount, currency, reference, metadata):
        """Process Paystack charge."""
        return {
            'status': 'success',
            'transaction_id': f'paystack_{reference}',
            'amount': str(amount),
            'currency': currency,
            'reference': reference,
            'timestamp': __import__('datetime').datetime.now().isoformat()
        }
    
    def refund(self, transaction_id, amount, reason):
        """Process Paystack refund."""
        return {
            'status': 'success',
            'refund_id': f'refund_{transaction_id}',
            'amount': str(amount)
        }
    
    def verify_webhook(self, payload, signature):
        """Verify Paystack webhook."""
        expected_sig = hmac.new(
            self.api_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, signature)


class PaymentProcessorFactory:
    """Factory for creating payment processors."""
    
    PROCESSORS = {
        'stripe': StripeProcessor,
        'paypal': PayPalProcessor,
        'flutterwave': FlutterwaveProcessor,
        'paystack': PaystackProcessor,
    }
    
    @classmethod
    def get_processor(cls, gateway, api_key, api_secret):
        """Get processor for gateway."""
        processor_class = cls.PROCESSORS.get(gateway.lower())
        if not processor_class:
            raise ValueError(f'Unknown payment gateway: {gateway}')
        return processor_class(api_key, api_secret)
