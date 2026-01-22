"""
Phase 8 Task 1: Threat Detection
Automated threat detection and incident response
"""

from datetime import timedelta
from django.utils import timezone
from django.db.models import Count
from .models import AccessLog, AuditLog, ThreatDetectionConfig, IncidentTicket
import logging

logger = logging.getLogger(__name__)


class ThreatDetector:
    """Detect and respond to security threats"""
    
    @staticmethod
    def check_brute_force():
        """Detect brute force attacks"""
        config = ThreatDetectionConfig.objects.filter(
            threat_type='BRUTE_FORCE',
            enabled=True
        ).first()
        
        if not config:
            return
        
        # Check for multiple failed logins from same IP
        time_window = timezone.now() - timedelta(seconds=config.time_window)
        
        failed_logins = AccessLog.objects.filter(
            access_type='FAILED_LOGIN',
            timestamp__gte=time_window,
            status='FAILURE'
        ).values('ip_address').annotate(count=Count('id'))
        
        for record in failed_logins:
            if record['count'] >= config.threshold:
                ip = record['ip_address']
                logger.warning(f"Brute force detected from {ip}")
                
                # Create incident
                ThreatDetector.create_incident(
                    'BRUTE_FORCE',
                    f"Brute force attack: {record['count']} failed logins from {ip}",
                    'CRITICAL',
                    config
                )
    
    @staticmethod
    def check_data_exfiltration():
        """Detect suspicious data export"""
        config = ThreatDetectionConfig.objects.filter(
            threat_type='DATA_EXFIL',
            enabled=True
        ).first()
        
        if not config:
            return
        
        time_window = timezone.now() - timedelta(seconds=config.time_window)
        
        # Check for unusual export activity
        exports = AccessLog.objects.filter(
            access_type='EXPORT',
            timestamp__gte=time_window
        ).values('user').annotate(count=Count('id'))
        
        for record in exports:
            if record['count'] >= config.threshold:
                logger.warning(f"Suspicious export activity by user {record['user']}")
                ThreatDetector.create_incident(
                    'DATA_EXFIL',
                    f"Suspicious export: {record['count']} exports",
                    'HIGH',
                    config
                )
    
    @staticmethod
    def check_privilege_escalation():
        """Detect privilege escalation attempts"""
        config = ThreatDetectionConfig.objects.filter(
            threat_type='PRIVILEGE_ESCALATION',
            enabled=True
        ).first()
        
        if not config:
            return
        
        time_window = timezone.now() - timedelta(seconds=config.time_window)
        
        # Check for permission changes by unprivileged users
        priv_escalations = AuditLog.objects.filter(
            action='UPDATE',
            model_name='user',
            timestamp__gte=time_window
        ).exclude(user__is_staff=True)
        
        if priv_escalations.exists():
            for log in priv_escalations:
                logger.warning(f"Privilege escalation attempt by {log.user}")
                ThreatDetector.create_incident(
                    'PRIVILEGE_ESCALATION',
                    f"Attempted privilege escalation by {log.user}",
                    'CRITICAL',
                    config
                )
    
    @staticmethod
    def check_anomalous_access():
        """Detect anomalous access patterns"""
        config = ThreatDetectionConfig.objects.filter(
            threat_type='ANOMALOUS_ACCESS',
            enabled=True
        ).first()
        
        if not config:
            return
        
        time_window = timezone.now() - timedelta(seconds=config.time_window)
        
        # Check for access outside normal business hours
        for hour in range(23, 6):  # 11 PM to 6 AM
            accesses = AccessLog.objects.filter(
                timestamp__hour=hour,
                timestamp__gte=time_window
            ).values('user').annotate(count=Count('id'))
            
            for record in accesses:
                if record['count'] >= config.threshold:
                    logger.warning(f"Anomalous access pattern for user {record['user']}")
    
    @staticmethod
    def check_rate_limit_violation():
        """Detect rate limit violations"""
        config = ThreatDetectionConfig.objects.filter(
            threat_type='RATE_LIMIT_VIOLATION',
            enabled=True
        ).first()
        
        if not config:
            return
        
        time_window = timezone.now() - timedelta(seconds=config.time_window)
        
        # Check for excessive requests from single IP
        ips = AccessLog.objects.filter(
            timestamp__gte=time_window
        ).values('ip_address').annotate(count=Count('id'))
        
        for record in ips:
            if record['count'] >= config.threshold:
                logger.warning(f"Rate limit violation from {record['ip_address']}")
                ThreatDetector.create_incident(
                    'RATE_LIMIT_VIOLATION',
                    f"Rate limit exceeded: {record['count']} requests",
                    'MEDIUM',
                    config
                )
    
    @staticmethod
    def create_incident(threat_type, description, severity, config):
        """Create incident ticket"""
        incident_id = f"INC-{timezone.now().strftime('%Y%m%d%H%M%S')}-{threat_type[:3]}"
        
        IncidentTicket.objects.create(
            incident_id=incident_id,
            title=threat_type,
            description=description,
            severity=severity,
            notes=f"Detected by: {threat_type} detector"
        )
        
        # Send alert if configured
        if config.alert_email:
            ThreatDetector.send_alert(config.alert_email, incident_id, description)
    
    @staticmethod
    def send_alert(email, incident_id, description):
        """Send security alert"""
        from django.core.mail import send_mail
        
        subject = f"Security Alert: {incident_id}"
        message = f"""
        Security Incident Detected
        
        Incident ID: {incident_id}
        Description: {description}
        Timestamp: {timezone.now()}
        
        Please investigate immediately.
        """
        
        try:
            send_mail(subject, message, 'security@school.local', [email])
        except Exception as e:
            logger.error(f"Failed to send alert: {str(e)}")
