"""
Phase 8 Task 10: GeoIP & Regional Support
Geographic IP detection, location-based access control, region customization
"""

import geoip2.database
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.functional import cached_property
import requests
from typing import Optional, Dict, List, Tuple
import json

try:
    from django.contrib.gis.geos import Point
    from django.contrib.gis.db import models as gis_models
except (ImportError, ImproperlyConfigured):
    Point = None

    class _DummyGIS:
        PointField = models.JSONField

    gis_models = _DummyGIS()


class RegionalConfig(models.Model):
    """Regional configuration settings"""
    
    REGION_CHOICES = [
        ('WEST_AFRICA', 'West Africa'),
        ('EAST_AFRICA', 'East Africa'),
        ('SOUTHERN_AFRICA', 'Southern Africa'),
        ('CENTRAL_AFRICA', 'Central Africa'),
        ('NORTH_AFRICA', 'North Africa'),
    ]
    
    region = models.CharField(max_length=20, choices=REGION_CHOICES, unique=True)
    currency = models.CharField(max_length=3, default='USD')
    language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='UTC')
    countries = models.JSONField(default=list)  # List of country codes
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Regional Configs"
    
    def __str__(self):
        return f"{self.region} ({self.currency})"


class IPWhitelist(models.Model):
    """IP whitelist for regional access"""
    
    ip_address = models.GenericIPAddressField(unique=True)
    region = models.ForeignKey(RegionalConfig, on_delete=models.CASCADE)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.ip_address} - {self.region}"


class GeoIPLocation(models.Model):
    """Cached GeoIP location data"""
    
    ip_address = models.GenericIPAddressField(unique=True, db_index=True)
    country_code = models.CharField(max_length=2)
    country_name = models.CharField(max_length=100)
    city = models.CharField(max_length=100, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    location = gis_models.PointField(null=True)
    timezone = models.CharField(max_length=50, blank=True)
    isp = models.CharField(max_length=100, blank=True)
    is_vpn = models.BooleanField(default=False)
    is_proxy = models.BooleanField(default=False)
    last_checked = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['country_code']),
            models.Index(fields=['ip_address']),
        ]
    
    def __str__(self):
        return f"{self.ip_address} - {self.country_name}"


class RegionalAccessPolicy(models.Model):
    """Define access policies per region"""
    
    ACCESS_TYPES = [
        ('ALLOW', 'Allow'),
        ('DENY', 'Deny'),
        ('RESTRICT', 'Restrict'),
    ]
    
    region = models.ForeignKey(RegionalConfig, on_delete=models.CASCADE)
    access_type = models.CharField(max_length=10, choices=ACCESS_TYPES)
    require_vpn = models.BooleanField(default=False)
    data_residency_required = models.BooleanField(default=False)
    user_groups = models.JSONField(default=list)  # List of user groups allowed
    ip_ranges = models.JSONField(default=list)  # CIDR ranges
    rate_limit_per_hour = models.IntegerField(default=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('region', 'access_type')
    
    def __str__(self):
        return f"{self.region} - {self.access_type}"


class GeoIPService:
    """Service for GeoIP lookups and regional operations"""
    
    MAXMIND_DB_PATH = 'geoip/GeoLite2-City.mmdb'
    CACHE_TIMEOUT = 86400  # 24 hours
    
    @staticmethod
    def lookup_ip(ip_address: str) -> Optional[Dict]:
        """Lookup IP geolocation"""
        cache_key = f'geoip:{ip_address}'
        
        # Check cache first
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        try:
            # Try to get from database
            location = GeoIPLocation.objects.get(ip_address=ip_address)
            result = {
                'ip': ip_address,
                'country_code': location.country_code,
                'country_name': location.country_name,
                'city': location.city,
                'latitude': location.latitude,
                'longitude': location.longitude,
                'timezone': location.timezone,
                'isp': location.isp,
                'is_vpn': location.is_vpn,
                'is_proxy': location.is_proxy,
            }
            cache.set(cache_key, result, GeoIPService.CACHE_TIMEOUT)
            return result
        except GeoIPLocation.DoesNotExist:
            # Query external service or MaxMind DB
            return None
    
    @staticmethod
    def get_user_region(ip_address: str) -> Optional[str]:
        """Get region from IP address"""
        location = GeoIPService.lookup_ip(ip_address)
        if not location:
            return None
        
        configs = RegionalConfig.objects.filter(
            is_active=True
        )
        country_code = location.get('country_code')
        for config in configs:
            countries = config.countries or []
            if country_code in countries:
                return config.region

        return None
    
    @staticmethod
    def is_ip_whitelisted(ip_address: str) -> bool:
        """Check if IP is whitelisted"""
        return IPWhitelist.objects.filter(
            ip_address=ip_address,
            is_active=True
        ).exists()
    
    @staticmethod
    def check_region_access(region: str, user_group: str) -> bool:
        """Check if user group has access to region"""
        try:
            policy = RegionalAccessPolicy.objects.get(
                region__region=region,
                access_type='ALLOW'
            )
            return user_group in policy.user_groups
        except RegionalAccessPolicy.DoesNotExist:
            return False
    
    @staticmethod
    def get_region_config(region: str) -> Optional[RegionalConfig]:
        """Get configuration for region"""
        cache_key = f'region_config:{region}'
        
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        try:
            config = RegionalConfig.objects.get(region=region, is_active=True)
            cache.set(cache_key, config, GeoIPService.CACHE_TIMEOUT)
            return config
        except RegionalConfig.DoesNotExist:
            return None
    
    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates (km)"""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth radius in km
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c
        
        return distance


class LocationBasedAccessControl:
    """Control access based on geolocation"""
    
    def __init__(self, ip_address: str):
        self.ip_address = ip_address
        self.location = GeoIPService.lookup_ip(ip_address)
        self.region = GeoIPService.get_user_region(ip_address)
    
    def is_allowed(self, required_region: Optional[str] = None) -> bool:
        """Check if access is allowed"""
        if not self.location:
            return False
        
        # Check whitelist
        if GeoIPService.is_ip_whitelisted(self.ip_address):
            return True
        
        # Check VPN/Proxy
        if self.location.get('is_vpn') or self.location.get('is_proxy'):
            return False
        
        # Check region
        if required_region and self.region != required_region:
            return False
        
        return True
    
    def get_access_level(self) -> str:
        """Get access level (full, restricted, denied)"""
        if not self.location:
            return 'denied'
        
        if GeoIPService.is_ip_whitelisted(self.ip_address):
            return 'full'
        
        if self.location.get('is_vpn'):
            return 'restricted'
        
        return 'full'
    
    def enforce_data_residency(self, data_region: str) -> bool:
        """Check data residency requirement"""
        if not self.region:
            return False
        
        config = GeoIPService.get_region_config(self.region)
        if not config:
            return False
        
        return config.region == data_region


class RegionalDataLocalization:
    """Localize data based on regional requirements"""
    
    REGIONAL_CURRENCIES = {
        'WEST_AFRICA': {'NGN', 'GHS', 'SLL', 'GMD', 'CVE'},
        'EAST_AFRICA': {'KES', 'UGX', 'TZS', 'RWF', 'BIF'},
        'SOUTHERN_AFRICA': {'ZAR', 'BWP', 'ZWL', 'NAD', 'LSL'},
        'CENTRAL_AFRICA': {'XAF', 'XOF', 'CDF', 'AOA'},
        'NORTH_AFRICA': {'EGP', 'TND', 'DZD', 'MAD', 'LYD'},
    }
    
    REGIONAL_LANGUAGES = {
        'WEST_AFRICA': ['en', 'fr', 'ha', 'yo'],
        'EAST_AFRICA': ['en', 'sw', 'am'],
        'SOUTHERN_AFRICA': ['en', 'zu', 'xh', 'st'],
        'CENTRAL_AFRICA': ['fr', 'en', 'lin'],
        'NORTH_AFRICA': ['ar', 'fr', 'en'],
    }
    
    @staticmethod
    def get_regional_currency(region: str) -> str:
        """Get default currency for region"""
        config = GeoIPService.get_region_config(region)
        return config.currency if config else 'USD'
    
    @staticmethod
    def get_regional_languages(region: str) -> List[str]:
        """Get supported languages for region"""
        return RegionalDataLocalization.REGIONAL_LANGUAGES.get(region, ['en'])
    
    @staticmethod
    def get_regional_timezone(region: str) -> str:
        """Get timezone for region"""
        config = GeoIPService.get_region_config(region)
        return config.timezone if config else 'UTC'
    
    @staticmethod
    def format_currency(amount: float, region: str, decimal_places: int = 2) -> str:
        """Format currency based on region"""
        currency = RegionalDataLocalization.get_regional_currency(region)
        
        CURRENCY_SYMBOLS = {
            'NGN': '₦', 'GHS': '₵', 'KES': 'KSh',
            'ZAR': 'R', 'EGP': 'E£', 'USD': '$',
        }
        
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        formatted_amount = f"{amount:,.{decimal_places}f}"
        return f"{symbol}{formatted_amount}"
    
    @staticmethod
    def apply_regional_rules(user_id: int, ip_address: str) -> Dict:
        """Apply all regional rules to user"""
        region = GeoIPService.get_user_region(ip_address)
        
        return {
            'region': region,
            'currency': RegionalDataLocalization.get_regional_currency(region),
            'languages': RegionalDataLocalization.get_regional_languages(region),
            'timezone': RegionalDataLocalization.get_regional_timezone(region),
        }


class GeoIPEventLogger:
    """Log location-based events"""
    
    @staticmethod
    def log_access(ip_address: str, user_id: int, resource: str, allowed: bool):
        """Log access attempt"""
        location = GeoIPService.lookup_ip(ip_address)
        if not location:
            return
        
        from django.contrib.admin.models import LogEntry, CHANGE
        from django.contrib.contenttypes.models import ContentType
        
        event = {
            'timestamp': timezone.now(),
            'ip': ip_address,
            'user': user_id,
            'resource': resource,
            'allowed': allowed,
            'country': location['country_code'],
            'city': location['city'],
        }
        
        # Store in cache or database
        cache.set(f'geo_event:{ip_address}:{user_id}:{resource}', event, 86400)
    
    @staticmethod
    def get_access_summary(days: int = 30) -> Dict:
        """Get summary of access patterns"""
        # Query recent access logs
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff = timezone.now() - timedelta(days=days)
        
        return {
            'period_days': days,
            'total_access_attempts': 0,
            'allowed': 0,
            'denied': 0,
            'vpn_detected': 0,
        }


# Import timezone at module level
from django.utils import timezone
