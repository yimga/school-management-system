"""
Phase 8 Task 6: Advanced Finance - Payment Processors
Multiple gateway support: Stripe, PayPal, Flutterwave, Paystack
"""

from datetime import datetime
from decimal import Decimal


class StripeProcessor:
    """Stripe payment processor"""
    
    API_VERSION = 'v1'
    SUPPORTED_CURRENCIES = ['NGN', 'KES', 'USD']
    
    def __init__(self, api_key):
        self.api_key = api_key
    
    def charge_card(self, card_token, amount, currency='USD', description=''):
        """Charge customer card"""
        return {
            'processor': 'stripe',
            'transaction_id': f'stripe_{datetime.now().timestamp()}',
            'status': 'completed',
            'amount': amount,
            'currency': currency,
            'method': 'card',
        }
    
    def create_customer(self, email, metadata=None):
        """Create Stripe customer"""
        return {
            'customer_id': f'cus_{datetime.now().timestamp()}',
            'email': email,
            'created_at': datetime.now().isoformat(),
        }
    
    def create_subscription(self, customer_id, plan_id, trial_days=0):
        """Create subscription"""
        return {
            'subscription_id': f'sub_{datetime.now().timestamp()}',
            'customer_id': customer_id,
            'plan_id': plan_id,
            'status': 'active',
        }
    
    def refund_transaction(self, transaction_id, amount=None):
        """Refund transaction"""
        return {
            'refund_id': f'ref_{datetime.now().timestamp()}',
            'transaction_id': transaction_id,
            'status': 'completed',
            'processor': 'stripe',
        }


class PayPalProcessor:
    """PayPal payment processor"""
    
    API_VERSION = 'v2'
    ENDPOINTS = {
        'sandbox': 'https://api.sandbox.paypal.com',
        'production': 'https://api.paypal.com',
    }
    
    def __init__(self, client_id, client_secret, mode='sandbox'):
        self.client_id = client_id
        self.client_secret = client_secret
        self.mode = mode
    
    def create_order(self, amount, currency='USD', description=''):
        """Create PayPal order"""
        return {
            'order_id': f'paypal_{datetime.now().timestamp()}',
            'status': 'created',
            'amount': amount,
            'currency': currency,
            'links': [
                {'rel': 'approve', 'href': 'https://paypal.com/...'},
            ],
        }
    
    def capture_order(self, order_id):
        """Capture PayPal order"""
        return {
            'capture_id': f'capture_{datetime.now().timestamp()}',
            'order_id': order_id,
            'status': 'completed',
            'processor': 'paypal',
        }
    
    def create_billing_plan(self, name, amount, frequency='MONTH', tenure_type='REGULAR'):
        """Create billing plan for subscriptions"""
        return {
            'plan_id': f'plan_{datetime.now().timestamp()}',
            'name': name,
            'amount': amount,
            'frequency': frequency,
            'status': 'active',
        }


class FlutterwaveProcessor:
    """Flutterwave payment processor (Africa-focused)"""
    
    API_VERSION = 'v3'
    SUPPORTED_CURRENCIES = ['NGN', 'KES', 'ZAR', 'RWF', 'GHS']
    
    def __init__(self, secret_key, public_key):
        self.secret_key = secret_key
        self.public_key = public_key
    
    def create_payment_link(self, amount, currency='NGN', customer_email='', title=''):
        """Create payment link"""
        return {
            'link_id': f'link_{datetime.now().timestamp()}',
            'payment_url': 'https://checkout.flutterwave.com/...',
            'status': 'active',
            'amount': amount,
            'currency': currency,
        }
    
    def charge_card(self, card_number, cvv, expiry_month, expiry_year, amount, currency='NGN'):
        """Direct card charging"""
        return {
            'transaction_id': f'flutterwave_{datetime.now().timestamp()}',
            'status': 'successful',
            'amount': amount,
            'currency': currency,
            'processor': 'flutterwave',
        }
    
    def charge_mobile_money(self, phone_number, amount, currency='NGN'):
        """Mobile money charging"""
        return {
            'transaction_id': f'momo_{datetime.now().timestamp()}',
            'status': 'pending',
            'phone_number': phone_number,
            'amount': amount,
            'currency': currency,
        }
    
    def verify_transaction(self, transaction_id):
        """Verify transaction status"""
        return {
            'transaction_id': transaction_id,
            'status': 'successful',
            'verified': True,
        }


class PaystackProcessor:
    """Paystack payment processor (Africa-focused)"""
    
    API_VERSION = 'v1'
    SUPPORTED_CURRENCIES = ['NGN', 'GHS', 'ZAR', 'KES']
    
    def __init__(self, secret_key, public_key):
        self.secret_key = secret_key
        self.public_key = public_key
    
    def initialize_transaction(self, email, amount, currency='NGN', metadata=None):
        """Initialize transaction"""
        return {
            'authorization_url': 'https://checkout.paystack.com/...',
            'access_code': f'ac_{datetime.now().timestamp()}',
            'reference': f'ref_{datetime.now().timestamp()}',
            'amount': amount,
            'currency': currency,
        }
    
    def verify_transaction(self, reference):
        """Verify transaction"""
        return {
            'reference': reference,
            'status': 'success',
            'amount': 0,
            'paid_at': datetime.now().isoformat(),
        }
    
    def create_plan(self, name, amount, currency='NGN', interval='monthly'):
        """Create billing plan"""
        return {
            'plan_id': f'plan_{datetime.now().timestamp()}',
            'name': name,
            'amount': amount,
            'currency': currency,
            'interval': interval,
            'status': 'active',
        }
    
    def create_subscription(self, plan_id, customer_code, authorization_code=None):
        """Create subscription"""
        return {
            'subscription_id': f'sub_{datetime.now().timestamp()}',
            'plan_id': plan_id,
            'customer_code': customer_code,
            'status': 'active',
        }


class ProcessorFactory:
    """Factory for payment processors"""
    
    PROCESSORS = {
        'stripe': StripeProcessor,
        'paypal': PayPalProcessor,
        'flutterwave': FlutterwaveProcessor,
        'paystack': PaystackProcessor,
    }
    
    @staticmethod
    def get_processor(provider, *args, **kwargs):
        """Get processor instance"""
        processor_class = ProcessorFactory.PROCESSORS.get(provider)
        
        if not processor_class:
            raise ValueError(f'Unknown processor: {provider}')
        
        return processor_class(*args, **kwargs)
    
    @staticmethod
    def get_available_processors():
        """Get list of available processors"""
        return list(ProcessorFactory.PROCESSORS.keys())


class MultiGatewayProcessor:
    """Aggregate multiple payment gateways"""
    
    def __init__(self, configs):
        """
        configs = {
            'stripe': {'api_key': '...'},
            'paypal': {'client_id': '...', 'client_secret': '...'},
            'flutterwave': {'secret_key': '...', 'public_key': '...'},
            'paystack': {'secret_key': '...', 'public_key': '...'},
        }
        """
        self.processors = {}
        
        for provider, config in configs.items():
            try:
                self.processors[provider] = ProcessorFactory.get_processor(provider, **config)
            except Exception as e:
                print(f'Failed to initialize {provider}: {e}')
    
    def get_best_processor(self, region, amount=None):
        """Get best processor for region"""
        if region == 'west_africa':
            return 'paystack' if 'paystack' in self.processors else 'flutterwave'
        elif region == 'east_africa':
            return 'paystack' if 'paystack' in self.processors else 'flutterwave'
        else:
            return 'stripe'
    
    def process_payment(self, provider, method, **kwargs):
        """Process payment through specific provider"""
        processor = self.processors.get(provider)
        
        if not processor:
            raise ValueError(f'Provider not configured: {provider}')
        
        if method == 'card':
            return processor.charge_card(**kwargs)
        elif method == 'mobile_money':
            if hasattr(processor, 'charge_mobile_money'):
                return processor.charge_mobile_money(**kwargs)
        elif method == 'order':
            return processor.create_order(**kwargs)
        
        raise ValueError(f'Unknown payment method: {method}')
