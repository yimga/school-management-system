"""
Compliance Middleware: Comprehensive audit and access control
Logs all requests, tracks user activity, detects threats
"""

from django.utils.deprecation import MiddlewareNotUsed
from django.contrib.auth.models import AnonymousUser
from .models import AccessLog, AuditLog, ThreatDetectionConfig, IncidentTicket
import geoip2.database
import logging
from datetime import datetime, timedelta
from django.core.cache import cache
from django.db.models import Count

logger = logging.getLogger(__name__)


class ComplianceAuditMiddleware:
    """
    Middleware to log all access and detect threats
    Implements:
    - Request logging
    - User activity tracking
    - Threat detection
    - Rate limiting
    - Geographic tracking
    """
    
    EXCLUDED_PATHS = ['/static/', '/media/', '/health/']
    SENSITIVE_METHODS = ['POST', 'DELETE', 'PUT']
    SENSITIVE_ENDPOINTS = ['/admin/', '/api/grades/', '/api/finance/', '/authentication/']
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.geoip_reader = None
        try:
            self.geoip_reader = geoip2.database.Reader('/path/to/GeoLite2-City.mmdb')
        except:
            logger.warning("GeoIP database not available")
    
    def __call__(self, request):
        # Skip excluded paths
        if any(request.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return self.get_response(request)
        
        # Pre-request processing
        self.log_access(request)
        self.check_threats(request)
        
        # Get response
        response = self.get_response(request)
        
        # Post-request processing
        self.log_sensitive_changes(request, response)
        
        return response
    
    def log_access(self, request):
        """Log all access attempts"""
        try:
            ip_address = self.get_client_ip(request)
            access_type = self.determine_access_type(request)
            
            country = self.get_country_from_ip(ip_address)
            
            # Check if sensitive endpoint
            is_sensitive = any(
                request.path.startswith(ep) for ep in self.SENSITIVE_ENDPOINTS
            )
            
            if is_sensitive or request.method in self.SENSITIVE_METHODS:
                AccessLog.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    access_type=access_type,
                    resource=request.path,
                    ip_address=ip_address,
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                    country=country,
                    details={
                        'method': request.method,
                        'referer': request.META.get('HTTP_REFERER', ''),
                        'query_params': dict(request.GET.items()),
                    }
                )
        except Exception as e:
            logger.error(f"Error logging access: {str(e)}")
    
    def check_threats(self, request):
        """Detect and respond to threats"""
        ip_address = self.get_client_ip(request)
        
        # Brute force detection
        self.check_brute_force(ip_address, request)
        
        # Rate limiting
        self.check_rate_limit(ip_address, request)
        
        # Anomalous access
        self.check_anomalous_access(request)
    
    def check_brute_force(self, ip_address, request):
        """Detect brute force login attempts"""
        if 'login' not in request.path.lower():
            return
        
        cache_key = f"failed_login_{ip_address}"
        failed_count = cache.get(cache_key, 0)
        
        # If failed login, increment counter
        if request.method == 'POST':
            failed_count += 1
            cache.set(cache_key, failed_count, 3600)  # 1 hour
            
            # Threshold: 5 failed attempts
            if failed_count >= 5:
                self.create_incident_ticket(
                    'BRUTE_FORCE',
                    f"Brute force attack detected from {ip_address}",
                    'CRITICAL',
                    ip_address=ip_address
                )
    
    def check_rate_limit(self, ip_address, request):
        """Check for rate limit violations"""
        cache_key = f"rate_limit_{ip_address}"
        request_count = cache.get(cache_key, 0)
        
        # 100 requests per minute per IP
        if request_count > 100:
            logger.warning(f"Rate limit exceeded for {ip_address}")
        
        cache.set(cache_key, request_count + 1, 60)
    
    def check_anomalous_access(self, request):
        """Detect anomalous access patterns"""
        user = request.user
        
        if not user.is_authenticated:
            return
        
        # Check if accessing data outside normal hours
        current_hour = datetime.now().hour
        if current_hour < 6 or current_hour > 22:  # Outside 6 AM - 10 PM
            recent_access = AccessLog.objects.filter(
                user=user,
                timestamp__gte=datetime.now() - timedelta(hours=1)
            ).count()
            
            if recent_access > 10:  # More than 10 accesses in last hour
                logger.warning(f"Anomalous access pattern for {user}")
    
    def log_sensitive_changes(self, request, response):
        """Log sensitive data modifications"""
        if request.method not in self.SENSITIVE_METHODS:
            return
        
        ip_address = self.get_client_ip(request)
        
        # Log sensitive operations
        if any(request.path.startswith(ep) for ep in self.SENSITIVE_ENDPOINTS):
            AccessLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                access_type='SENSITIVE_OPERATION',
                resource=request.path,
                ip_address=ip_address,
                status='SUCCESS' if response.status_code < 400 else 'FAILURE',
            )
    
    def determine_access_type(self, request):
        """Determine the type of access"""
        path = request.path.lower()
        
        if 'login' in path:
            return 'LOGIN'
        elif 'logout' in path:
            return 'LOGOUT'
        elif 'grade' in path or 'eval' in path:
            return 'GRADE_VIEW'
        elif 'finance' in path or 'invoice' in path or 'payment' in path:
            return 'FINANCE_VIEW'
        elif '/admin/' in path:
            return 'ADMIN_ACCESS'
        elif 'export' in path:
            return 'EXPORT'
        elif 'import' in path:
            return 'IMPORT'
        elif 'report' in path:
            return 'REPORT_DOWNLOAD'
        elif '/api/' in path:
            return 'API_CALL'
        else:
            return 'DATA_ACCESS'
    
    def get_client_ip(self, request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_country_from_ip(self, ip_address):
        """Get country code from IP address"""
        if not self.geoip_reader:
            return ''
        
        try:
            response = self.geoip_reader.city(ip_address)
            return response.country.iso_code
        except:
            return ''
    
    def create_incident_ticket(self, threat_type, description, severity, **kwargs):
        """Create incident ticket for threats"""
        try:
            incident_id = f"INC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            IncidentTicket.objects.create(
                incident_id=incident_id,
                title=threat_type,
                description=description,
                severity=severity,
                notes=f"IP: {kwargs.get('ip_address', 'Unknown')}"
            )
        except Exception as e:
            logger.error(f"Error creating incident ticket: {str(e)}")
