"""
Phase 8 Task 10: GeoIP & Regional Support Tests
Geographic IP detection, regional access control tests
"""

from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache


class RegionalConfigTestCase(TestCase):
    """Test regional configuration"""
    
    def test_create_region(self):
        """Test creating regional config"""
        from apps.siteconfig.geoip_service import RegionalConfig
        
        config = RegionalConfig.objects.create(
            region='WEST_AFRICA',
            currency='NGN',
            language='en',
            timezone='Africa/Lagos',
            countries=['NG', 'GH', 'SL']
        )
        
        self.assertEqual(config.currency, 'NGN')
        self.assertEqual(len(config.countries), 3)
    
    def test_region_uniqueness(self):
        """Test region uniqueness"""
        from apps.siteconfig.geoip_service import RegionalConfig
        
        RegionalConfig.objects.create(
            region='EAST_AFRICA',
            currency='KES'
        )
        
        with self.assertRaises(Exception):
            RegionalConfig.objects.create(
                region='EAST_AFRICA',
                currency='UGX'
            )


class IPWhitelistTestCase(TestCase):
    """Test IP whitelist"""
    
    def setUp(self):
        from apps.siteconfig.geoip_service import RegionalConfig, IPWhitelist
        
        self.region = RegionalConfig.objects.create(
            region='WEST_AFRICA',
            currency='NGN'
        )
    
    def test_add_to_whitelist(self):
        """Test adding IP to whitelist"""
        from apps.siteconfig.geoip_service import IPWhitelist
        
        whitelist = IPWhitelist.objects.create(
            ip_address='192.168.1.1',
            region=self.region
        )
        
        self.assertTrue(whitelist.is_active)
    
    def test_whitelist_query(self):
        """Test whitelist lookup"""
        from apps.siteconfig.geoip_service import IPWhitelist, GeoIPService
        
        IPWhitelist.objects.create(
            ip_address='10.0.0.1',
            region=self.region
        )
        
        self.assertTrue(GeoIPService.is_ip_whitelisted('10.0.0.1'))
        self.assertFalse(GeoIPService.is_ip_whitelisted('10.0.0.2'))


class GeoIPLocationTestCase(TestCase):
    """Test GeoIP location caching"""
    
    def test_create_location(self):
        """Test creating location record"""
        from apps.siteconfig.geoip_service import GeoIPLocation
        
        location = GeoIPLocation.objects.create(
            ip_address='203.0.113.1',
            country_code='NG',
            country_name='Nigeria',
            city='Lagos',
            latitude=6.5244,
            longitude=3.3792,
            timezone='Africa/Lagos'
        )
        
        self.assertEqual(location.country_code, 'NG')
        self.assertEqual(location.city, 'Lagos')
    
    def test_location_indexing(self):
        """Test location database indexes"""
        from apps.siteconfig.geoip_service import GeoIPLocation
        
        GeoIPLocation.objects.create(
            ip_address='203.0.113.2',
            country_code='KE',
            country_name='Kenya',
            latitude=1.2921,
            longitude=36.8219
        )
        
        result = GeoIPLocation.objects.filter(country_code='KE').first()
        self.assertIsNotNone(result)


class RegionalAccessPolicyTestCase(TestCase):
    """Test regional access policies"""
    
    def setUp(self):
        from apps.siteconfig.geoip_service import RegionalConfig, RegionalAccessPolicy
        
        self.region = RegionalConfig.objects.create(
            region='SOUTHERN_AFRICA',
            currency='ZAR'
        )
    
    def test_create_policy(self):
        """Test creating access policy"""
        from apps.siteconfig.geoip_service import RegionalAccessPolicy
        
        policy = RegionalAccessPolicy.objects.create(
            region=self.region,
            access_type='ALLOW',
            user_groups=['STUDENT', 'TEACHER'],
            rate_limit_per_hour=1000
        )
        
        self.assertEqual(policy.access_type, 'ALLOW')
        self.assertEqual(len(policy.user_groups), 2)


class GeoIPServiceTestCase(TestCase):
    """Test GeoIP service"""
    
    def setUp(self):
        from apps.siteconfig.geoip_service import RegionalConfig, GeoIPLocation
        
        self.region = RegionalConfig.objects.create(
            region='WEST_AFRICA',
            currency='NGN',
            timezone='Africa/Lagos',
            countries=['NG', 'GH']
        )
        
        GeoIPLocation.objects.create(
            ip_address='203.0.113.10',
            country_code='NG',
            country_name='Nigeria',
            city='Lagos',
            latitude=6.5244,
            longitude=3.3792,
            timezone='Africa/Lagos'
        )
    
    def test_lookup_ip(self):
        """Test IP lookup"""
        from apps.siteconfig.geoip_service import GeoIPService
        
        result = GeoIPService.lookup_ip('203.0.113.10')
        
        self.assertIsNotNone(result)
        self.assertEqual(result['country_code'], 'NG')
    
    def test_get_user_region(self):
        """Test getting region from IP"""
        from apps.siteconfig.geoip_service import GeoIPService
        
        region = GeoIPService.get_user_region('203.0.113.10')
        
        self.assertEqual(region, 'WEST_AFRICA')
    
    def test_cache_behavior(self):
        """Test caching of IP lookups"""
        from apps.siteconfig.geoip_service import GeoIPService
        
        cache.clear()
        
        # First lookup
        result1 = GeoIPService.lookup_ip('203.0.113.10')
        
        # Second lookup (should be cached)
        result2 = GeoIPService.lookup_ip('203.0.113.10')
        
        self.assertEqual(result1, result2)


class LocationBasedAccessControlTestCase(TestCase):
    """Test location-based access control"""
    
    def setUp(self):
        from apps.siteconfig.geoip_service import RegionalConfig, GeoIPLocation, IPWhitelist
        
        self.region = RegionalConfig.objects.create(
            region='EAST_AFRICA',
            currency='KES'
        )
        
        GeoIPLocation.objects.create(
            ip_address='203.0.113.20',
            country_code='KE',
            country_name='Kenya',
            city='Nairobi',
            latitude=1.2921,
            longitude=36.8219,
            timezone='Africa/Nairobi'
        )
    
    def test_allowed_access(self):
        """Test allowed access"""
        from apps.siteconfig.geoip_service import LocationBasedAccessControl
        
        control = LocationBasedAccessControl('203.0.113.20')
        
        self.assertTrue(control.is_allowed())
    
    def test_access_level(self):
        """Test access level determination"""
        from apps.siteconfig.geoip_service import LocationBasedAccessControl
        
        control = LocationBasedAccessControl('203.0.113.20')
        
        self.assertEqual(control.get_access_level(), 'full')
    
    def test_whitelist_access(self):
        """Test whitelisted IP access"""
        from apps.siteconfig.geoip_service import LocationBasedAccessControl, IPWhitelist
        
        IPWhitelist.objects.create(
            ip_address='203.0.113.20',
            region=self.region
        )
        
        control = LocationBasedAccessControl('203.0.113.20')
        
        self.assertEqual(control.get_access_level(), 'full')


class RegionalDataLocalizationTestCase(TestCase):
    """Test regional data localization"""
    
    def setUp(self):
        from apps.siteconfig.geoip_service import RegionalConfig
        
        self.region = RegionalConfig.objects.create(
            region='WEST_AFRICA',
            currency='NGN',
            timezone='Africa/Lagos'
        )
    
    def test_get_currency(self):
        """Test getting regional currency"""
        from apps.siteconfig.geoip_service import RegionalDataLocalization
        
        currency = RegionalDataLocalization.get_regional_currency('WEST_AFRICA')
        
        self.assertEqual(currency, 'NGN')
    
    def test_get_languages(self):
        """Test getting regional languages"""
        from apps.siteconfig.geoip_service import RegionalDataLocalization
        
        languages = RegionalDataLocalization.get_regional_languages('WEST_AFRICA')
        
        self.assertIn('en', languages)
    
    def test_format_currency(self):
        """Test currency formatting"""
        from apps.siteconfig.geoip_service import RegionalDataLocalization
        
        formatted = RegionalDataLocalization.format_currency(1000.50, 'WEST_AFRICA')
        
        self.assertIn('₦', formatted)
        self.assertIn('1,000.50', formatted)
    
    def test_apply_regional_rules(self):
        """Test applying regional rules"""
        from apps.siteconfig.geoip_service import RegionalDataLocalization
        
        rules = RegionalDataLocalization.apply_regional_rules(1, '203.0.113.30')
        
        self.assertIn('currency', rules)
        self.assertIn('languages', rules)
        self.assertIn('timezone', rules)


class GeoIPEventLoggerTestCase(TestCase):
    """Test GeoIP event logging"""
    
    def setUp(self):
        from apps.siteconfig.geoip_service import RegionalConfig, GeoIPLocation
        
        self.region = RegionalConfig.objects.create(
            region='CENTRAL_AFRICA',
            currency='XAF'
        )
        
        GeoIPLocation.objects.create(
            ip_address='203.0.113.40',
            country_code='CM',
            country_name='Cameroon',
            city='Yaoundé',
            latitude=3.8480,
            longitude=11.5021
        )
    
    def test_log_access(self):
        """Test logging access"""
        from apps.siteconfig.geoip_service import GeoIPEventLogger
        
        GeoIPEventLogger.log_access(
            ip_address='203.0.113.40',
            user_id=1,
            resource='student_records',
            allowed=True
        )
        
        # Verify cache entry
        from django.core.cache import cache
        event = cache.get('geo_event:203.0.113.40:1:student_records')
        
        self.assertIsNotNone(event)
        self.assertTrue(event['allowed'])
    
    def test_access_summary(self):
        """Test access summary"""
        from apps.siteconfig.geoip_service import GeoIPEventLogger
        
        summary = GeoIPEventLogger.get_access_summary(days=30)
        
        self.assertIn('total_access_attempts', summary)
        self.assertIn('period_days', summary)
