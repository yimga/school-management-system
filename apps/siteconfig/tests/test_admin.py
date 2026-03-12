"""
Tests for regional configuration admin interface and management.
"""

from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.admin.sites import AdminSite

from apps.siteconfig.models import RegionConfig, GradingScaleConfig, HolidayCalendar
from apps.siteconfig.admin import RegionConfigAdmin, GradingScaleConfigAdmin, HolidayCalendarAdmin
from apps.academics.models import AcademicYear
from apps.schools.models import School
from datetime import date


class RegionConfigAdminTestCase(TestCase):
    """Test RegionConfig admin interface."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password'
        )
        self.client.login(username='admin', password='password')
        
        # Create test region
        self.region = RegionConfig.objects.create(
            code='TST',
            name='Test Region',
            timezone='UTC',
            date_format='YYYY-MM-DD',
            grading_scale='0-20',
            default_currency='USD',
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        
        # Create grading scales
        for i, scale_type in enumerate(['0-20', '0-100', '0-10', 'a-f', 'gpa']):
            GradingScaleConfig.objects.create(
                region=self.region,
                scale_type=scale_type,
                min_score=0,
                max_score=20 if scale_type == '0-20' else (100 if scale_type == '0-100' else (10 if scale_type == '0-10' else 5)),
                grade_a_min=16 if scale_type == '0-20' else 80,
                grade_b_min=14 if scale_type == '0-20' else 70,
                grade_c_min=12 if scale_type == '0-20' else 60,
                grade_d_min=10 if scale_type == '0-20' else 50,
                grade_f_min=0,
                display_format='0.00',
            )

    def test_region_list_view(self):
        """Test region list view in admin."""
        url = reverse('admin:global_registries_regionconfig_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TST')
        self.assertContains(response, 'Test Region')

    def test_region_change_view(self):
        """Test region change view in admin."""
        url = reverse('admin:siteconfig_regionconfig_change', args=[self.region.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.region.name)

    def test_region_add_view(self):
        """Test region add view in admin."""
        url = reverse('admin:siteconfig_regionconfig_add')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_clone_region_action(self):
        """Test clone region admin action."""
        admin_site = AdminSite()
        admin_obj = RegionConfigAdmin(RegionConfig, admin_site)
        
        # Get mock request
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.admin_user
        
        # Call action
        queryset = RegionConfig.objects.filter(pk=self.region.pk)
        result = admin_obj.clone_region(request, queryset)
        
        # Check new region was created
        cloned = RegionConfig.objects.get(code=f"{self.region.code}_COPY")
        self.assertEqual(cloned.name, f"{self.region.name} (Copy)")
        self.assertEqual(cloned.timezone, self.region.timezone)
        self.assertEqual(cloned.gradingscaleconfig_set.count(), 5)

    def test_validate_configuration_action(self):
        """Test validate configuration admin action."""
        admin_site = AdminSite()
        admin_obj = RegionConfigAdmin(RegionConfig, admin_site)
        
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.admin_user
        request._messages = None
        
        from django.contrib.messages.storage.fallback import FallbackStorage
        request._messages = FallbackStorage(request)
        
        # Call action
        queryset = RegionConfig.objects.filter(pk=self.region.pk)
        admin_obj.validate_configuration(request, queryset)
        # Should complete without error

    def test_export_config_action(self):
        """Test export config admin action."""
        admin_site = AdminSite()
        admin_obj = RegionConfigAdmin(RegionConfig, admin_site)
        
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.admin_user
        
        # Call action
        queryset = RegionConfig.objects.filter(pk=self.region.pk)
        response = admin_obj.export_config(request, queryset)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_region_display_methods(self):
        """Test region admin display methods."""
        admin_site = AdminSite()
        admin_obj = RegionConfigAdmin(RegionConfig, admin_site)
        
        # Test code_display
        display = admin_obj.code_display(self.region)
        self.assertIn('TST', display)
        
        # Test academic_start
        months = admin_obj.academic_start(self.region)
        self.assertEqual(months, 'Sep')
        
        # Test terms_count
        count = admin_obj.terms_count(self.region)
        self.assertIn('3 terms', count)
        
        # Test scales_status
        status = admin_obj.scales_status(self.region)
        self.assertIn('Complete', status)

    def test_region_search(self):
        """Test region search in admin."""
        url = reverse('admin:global_registries_regionconfig_changelist')
        response = self.client.get(url, {'q': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Region')

    def test_region_filter(self):
        """Test region filtering in admin."""
        url = reverse('admin:global_registries_regionconfig_changelist')
        response = self.client.get(url, {'grading_scale': '0-20'})
        self.assertEqual(response.status_code, 200)


class GradingScaleConfigAdminTestCase(TestCase):
    """Test GradingScaleConfig admin interface."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password'
        )
        self.client.login(username='admin', password='password')
        
        self.region = RegionConfig.objects.create(
            code='TST', name='Test', timezone='UTC', default_currency='USD',
            academic_year_start_month=9, term_count_per_year=3
        )
        
        self.scale = GradingScaleConfig.objects.create(
            region=self.region, scale_type='0-20', min_score=0, max_score=20,
            grade_a_min=16, grade_b_min=14, grade_c_min=12,
            grade_d_min=10, grade_f_min=0, display_format='0.00'
        )

    def test_scale_list_view(self):
        """Test grading scale list view in admin."""
        url = reverse('admin:siteconfig_gradingscaleconfig_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_scale_change_view(self):
        """Test grading scale change view in admin."""
        url = reverse('admin:siteconfig_gradingscaleconfig_change', args=[self.scale.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_scale_display_methods(self):
        """Test grading scale admin display methods."""
        admin_site = AdminSite()
        admin_obj = GradingScaleConfigAdmin(GradingScaleConfig, admin_site)
        
        # Test scale_type_display
        display = admin_obj.scale_type_display(self.scale)
        self.assertIn('0-20', display)
        
        # Test score_range
        range_str = admin_obj.score_range(self.scale)
        self.assertIn('0', range_str)
        self.assertIn('20', range_str)
        
        # Test grade_breakdown
        breakdown = admin_obj.grade_breakdown(self.scale)
        self.assertIn('A:', breakdown)

    def test_scale_filter(self):
        """Test grading scale filtering in admin."""
        url = reverse('admin:siteconfig_gradingscaleconfig_changelist')
        response = self.client.get(url, {'scale_type': '0-20'})
        self.assertEqual(response.status_code, 200)


@override_settings(ROOT_URLCONF="config.tenant_urls")
class HolidayCalendarAdminTestCase(TestCase):
    """Test HolidayCalendar admin interface."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password'
        )
        self.client.login(username='admin', password='password')
        
        self.region = RegionConfig.objects.create(
            code='TST', name='Test', timezone='UTC', default_currency='USD',
            academic_year_start_month=9, term_count_per_year=3
        )
        
        # Create academic year
        self.year = AcademicYear.objects.create(
            name='2024/2025', start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30), is_current=True
        )
        
        self.holiday = HolidayCalendar.objects.create(
            region=self.region, academic_year=self.year, name='Summer Break',
            date_start=date(2024, 7, 1), date_end=date(2024, 8, 31),
            holiday_type='school', is_working_day=False
        )

    def test_holiday_list_view(self):
        """Test holiday list view in admin."""
        url = reverse('admin:siteconfig_holidaycalendar_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_holiday_change_view(self):
        """Test holiday change view in admin."""
        url = reverse('admin:siteconfig_holidaycalendar_change', args=[self.holiday.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_holiday_display_methods(self):
        """Test holiday admin display methods."""
        admin_site = AdminSite()
        admin_obj = HolidayCalendarAdmin(HolidayCalendar, admin_site)
        
        # Test date_range
        date_range = admin_obj.date_range(self.holiday)
        self.assertIn('2024', date_range)
        
        # Test holiday_type_display
        holiday_type = admin_obj.holiday_type_display(self.holiday)
        self.assertIn('school', holiday_type.lower())
        
        # Test is_working_day_display
        working_day = admin_obj.is_working_day_display(self.holiday)
        self.assertIn('Off', working_day)
        
        # Test days_duration
        duration = admin_obj.days_duration(self.holiday)
        self.assertIn('62', duration)

    def test_holiday_actions(self):
        """Test holiday admin actions."""
        admin_site = AdminSite()
        admin_obj = HolidayCalendarAdmin(HolidayCalendar, admin_site)
        
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.admin_user
        request._messages = None
        
        from django.contrib.messages.storage.fallback import FallbackStorage
        request._messages = FallbackStorage(request)
        
        # Mark as working day
        queryset = HolidayCalendar.objects.filter(pk=self.holiday.pk)
        admin_obj.mark_as_working_day(request, queryset)
        
        self.holiday.refresh_from_db()
        self.assertTrue(self.holiday.is_working_day)
        
        # Mark as holiday
        admin_obj.mark_as_holiday(request, queryset)
        self.holiday.refresh_from_db()
        self.assertFalse(self.holiday.is_working_day)

    def test_holiday_filter(self):
        """Test holiday filtering in admin."""
        url = reverse('admin:siteconfig_holidaycalendar_changelist')
        response = self.client.get(url, {'holiday_type': 'school'})
        self.assertEqual(response.status_code, 200)


class ManagementCommandTestCase(TestCase):
    """Test management commands for regional configuration."""

    def setUp(self):
        """Set up test data."""
        self.region = RegionConfig.objects.create(
            code='CMR', name='Cameroon', timezone='Africa/Douala',
            date_format='DD/MM/YYYY', grading_scale='0-20',
            default_currency='XAF', academic_year_start_month=9,
            term_count_per_year=3
        )
        
        # Create grading scales
        for i, scale_type in enumerate(['0-20', '0-100', '0-10', 'a-f', 'gpa']):
            GradingScaleConfig.objects.create(
                region=self.region, scale_type=scale_type,
                min_score=0, max_score=20, grade_a_min=16,
                grade_b_min=14, grade_c_min=12, grade_d_min=10,
                grade_f_min=0, display_format='0.00'
            )

    def test_validate_regions_command(self):
        """Test validate_regions management command."""
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        call_command('validate_regions', stdout=out)
        output = out.getvalue()
        
        self.assertIn('CMR', output)
        self.assertIn('Cameroon', output)

    def test_clone_region_command(self):
        """Test clone_region management command."""
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        call_command('clone_region', 'CMR', 'USA', stdout=out)
        
        # Check new region was created
        new_region = RegionConfig.objects.get(code='USA')
        self.assertEqual(new_region.timezone, self.region.timezone)
        self.assertEqual(new_region.gradingscaleconfig_set.count(), 5)

    def test_export_config_command(self):
        """Test export_config management command."""
        from django.core.management import call_command
        from io import StringIO
        import json
        import os
        
        out = StringIO()
        test_file = 'test_export.json'
        
        try:
            call_command('export_config', '--format', 'json', '--output', test_file, stdout=out)
            
            # Check file was created
            self.assertTrue(os.path.exists(test_file))
            
            # Check file contents
            with open(test_file, 'r') as f:
                data = json.load(f)
            
            self.assertIn('regions', data)
            self.assertEqual(len(data['regions']), 1)
            self.assertEqual(data['regions'][0]['code'], 'CMR')
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_import_config_command(self):
        """Test import_config management command."""
        from django.core.management import call_command
        from io import StringIO
        import json
        import os
        
        # Create export file first
        export_file = 'test_import_export.json'
        out = StringIO()
        call_command('export_config', '--format', 'json', '--output', export_file, stdout=out)
        
        # Delete original region
        RegionConfig.objects.filter(code='CMR').delete()
        
        try:
            # Import file
            out = StringIO()
            call_command('import_config', export_file, '--merge', stdout=out)
            
            # Check region was imported
            region = RegionConfig.objects.get(code='CMR')
            self.assertEqual(region.name, 'Cameroon')
        finally:
            if os.path.exists(export_file):
                os.remove(export_file)
