"""
Management command to seed default regions and grading scales.
Phase 1.2.4: Internationalization & Multi-Region Support
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.siteconfig.models import RegionConfig, GradingScaleConfig


class Command(BaseCommand):
    help = 'Seed default regions and grading scales for internationalization'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Seeding regions and grading scales...\n')
        
        # Define regions
        regions = [
            {
                'code': 'CMR',
                'name': 'Cameroon',
                'default_language': 'en',
                'timezone': 'Africa/Douala',
                'date_format': 'DD/MM/YYYY',
                'grading_scale': '0-20',
                'default_currency': 'XAF',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            },
            {
                'code': 'USA',
                'name': 'United States',
                'default_language': 'en',
                'timezone': 'America/New_York',
                'date_format': 'MM/DD/YYYY',
                'grading_scale': '0-100',
                'default_currency': 'USD',
                'academic_year_start_month': 8,
                'term_count_per_year': 2,
            },
            {
                'code': 'GBR',
                'name': 'United Kingdom',
                'default_language': 'en',
                'timezone': 'Europe/London',
                'date_format': 'DD/MM/YYYY',
                'grading_scale': 'a-f',
                'default_currency': 'GBP',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            },
            {
                'code': 'KEN',
                'name': 'Kenya',
                'default_language': 'sw',
                'timezone': 'Africa/Nairobi',
                'date_format': 'DD/MM/YYYY',
                'grading_scale': '0-100',
                'default_currency': 'KES',
                'academic_year_start_month': 1,
                'term_count_per_year': 3,
            },
            {
                'code': 'NGA',
                'name': 'Nigeria',
                'default_language': 'en',
                'timezone': 'Africa/Lagos',
                'date_format': 'DD/MM/YYYY',
                'grading_scale': '0-100',
                'default_currency': 'NGN',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            },
            {
                'code': 'FRA',
                'name': 'France',
                'default_language': 'fr',
                'timezone': 'Europe/Paris',
                'date_format': 'DD/MM/YYYY',
                'grading_scale': '0-20',
                'default_currency': 'EUR',
                'academic_year_start_month': 9,
                'term_count_per_year': 3,
            },
            {
                'code': 'DEU',
                'name': 'Germany',
                'default_language': 'en',
                'timezone': 'Europe/Berlin',
                'date_format': 'DD.MM.YYYY',
                'grading_scale': '0-10',
                'default_currency': 'EUR',
                'academic_year_start_month': 8,
                'term_count_per_year': 2,
            },
        ]
        
        created_count = 0
        for region_data in regions:
            region, created = RegionConfig.objects.get_or_create(
                code=region_data['code'],
                defaults=region_data
            )
            if created:
                self.stdout.write(f'✓ Created region: {region.name} ({region.code})')
                created_count += 1
            else:
                self.stdout.write(f'• Region already exists: {region.name} ({region.code})')
        
        self.stdout.write(f'\nCreated {created_count} new regions.\n')
        
        # Define grading scales per region
        grading_configs = [
            # Cameroon (0-20)
            {
                'region_code': 'CMR',
                'scale_type': '0-20',
                'min_score': Decimal('0'),
                'max_score': Decimal('20'),
                'display_format': '{score:.0f}/20',
                'grade_a_min': Decimal('18'),
                'grade_b_min': Decimal('15'),
                'grade_c_min': Decimal('12'),
                'grade_d_min': Decimal('9'),
                'grade_f_min': Decimal('0'),
            },
            # USA/Kenya/Nigeria (0-100)
            {
                'region_code': 'USA',
                'scale_type': '0-100',
                'min_score': Decimal('0'),
                'max_score': Decimal('100'),
                'display_format': '{score:.0f}%',
                'grade_a_min': Decimal('90'),
                'grade_b_min': Decimal('80'),
                'grade_c_min': Decimal('70'),
                'grade_d_min': Decimal('60'),
                'grade_f_min': Decimal('0'),
            },
            {
                'region_code': 'KEN',
                'scale_type': '0-100',
                'min_score': Decimal('0'),
                'max_score': Decimal('100'),
                'display_format': '{score:.0f}%',
                'grade_a_min': Decimal('80'),
                'grade_b_min': Decimal('65'),
                'grade_c_min': Decimal('50'),
                'grade_d_min': Decimal('40'),
                'grade_f_min': Decimal('0'),
            },
            {
                'region_code': 'NGA',
                'scale_type': '0-100',
                'min_score': Decimal('0'),
                'max_score': Decimal('100'),
                'display_format': '{score:.0f}%',
                'grade_a_min': Decimal('90'),
                'grade_b_min': Decimal('80'),
                'grade_c_min': Decimal('70'),
                'grade_d_min': Decimal('60'),
                'grade_f_min': Decimal('0'),
            },
            # UK (A-F letter grades)
            {
                'region_code': 'GBR',
                'scale_type': 'a-f',
                'min_score': Decimal('0'),
                'max_score': Decimal('4'),
                'display_format': 'A-F',
                'grade_a_min': Decimal('4'),
                'grade_b_min': Decimal('3'),
                'grade_c_min': Decimal('2'),
                'grade_d_min': Decimal('1'),
                'grade_f_min': Decimal('0'),
            },
            # France (0-20)
            {
                'region_code': 'FRA',
                'scale_type': '0-20',
                'min_score': Decimal('0'),
                'max_score': Decimal('20'),
                'display_format': '{score:.1f}/20',
                'grade_a_min': Decimal('16'),
                'grade_b_min': Decimal('13'),
                'grade_c_min': Decimal('10'),
                'grade_d_min': Decimal('8'),
                'grade_f_min': Decimal('0'),
            },
            # Germany (0-10, inverted: lower is better)
            {
                'region_code': 'DEU',
                'scale_type': '0-10',
                'min_score': Decimal('1'),
                'max_score': Decimal('6'),
                'display_format': '{score:.1f}',
                'grade_a_min': Decimal('1'),      # 1 is best
                'grade_b_min': Decimal('2'),
                'grade_c_min': Decimal('3'),
                'grade_d_min': Decimal('4'),
                'grade_f_min': Decimal('5'),      # 5-6 is failing
            },
        ]
        
        grading_created = 0
        for config in grading_configs:
            region = RegionConfig.objects.get(code=config['region_code'])
            grading, created = GradingScaleConfig.objects.get_or_create(
                region=region,
                scale_type=config['scale_type'],
                defaults={
                    'min_score': config['min_score'],
                    'max_score': config['max_score'],
                    'display_format': config['display_format'],
                    'grade_a_min': config['grade_a_min'],
                    'grade_b_min': config['grade_b_min'],
                    'grade_c_min': config['grade_c_min'],
                    'grade_d_min': config['grade_d_min'],
                    'grade_f_min': config['grade_f_min'],
                }
            )
            if created:
                self.stdout.write(f'✓ Created grading scale: {region.name} - {config["scale_type"]}')
                grading_created += 1
            else:
                self.stdout.write(f'• Grading scale already exists: {region.name} - {config["scale_type"]}')
        
        self.stdout.write(f'\nCreated {grading_created} new grading scales.\n')
        self.stdout.write(self.style.SUCCESS('✓ Internationalization seed complete!'))
