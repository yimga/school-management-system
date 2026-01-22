"""
Import regional configurations from JSON or CSV format.
Usage: python manage.py import_config configs.json
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import json
import csv
from decimal import Decimal

from apps.siteconfig.models import RegionConfig, GradingScaleConfig


class Command(BaseCommand):
    help = 'Import regional configurations from JSON or CSV format'

    def add_arguments(self, parser):
        parser.add_argument('input_file', type=str, help='Input file (JSON or CSV)')
        parser.add_argument(
            '--merge',
            action='store_true',
            help='Merge with existing regions (update existing)',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing regions',
        )
        parser.add_argument(
            '--validate-only',
            action='store_true',
            help='Validate file without importing',
        )

    def handle(self, *args, **options):
        input_file = options['input_file']
        
        self.stdout.write(self.style.SUCCESS('\n📥 Regional Configuration Importer\n'))
        
        # Determine file format
        if input_file.endswith('.json'):
            file_format = 'json'
        elif input_file.endswith('.csv'):
            file_format = 'csv'
        else:
            raise CommandError("Unsupported file format. Use .json or .csv")
        
        self.stdout.write(f"Input File: {input_file}")
        self.stdout.write(f"Format:     {file_format.upper()}")
        self.stdout.write('-' * 60)
        
        try:
            if file_format == 'json':
                data = self._load_json(input_file)
                regions_to_import = data['regions']
            else:
                regions_to_import = self._load_csv(input_file)
            
            # Validate
            validation_errors = self._validate_import_data(regions_to_import)
            if validation_errors:
                self.stdout.write(self.style.ERROR(f"\n✗ Validation failed:"))
                for error in validation_errors:
                    self.stdout.write(f"  • {error}")
                return
            
            self.stdout.write(self.style.SUCCESS(f"✓ Validation passed for {len(regions_to_import)} region(s)\n"))
            
            if options['validate_only']:
                return
            
            # Check for conflicts
            conflicts = self._check_conflicts(regions_to_import, options)
            if conflicts:
                self.stdout.write(self.style.WARNING(f"\n⚠️  Found {len(conflicts)} conflict(s):"))
                for conflict in conflicts:
                    self.stdout.write(f"  • {conflict}")
                
                if not (options['merge'] or options['overwrite']):
                    self.stdout.write(self.style.ERROR("\nUse --merge or --overwrite to proceed"))
                    return
            
            # Import
            with transaction.atomic():
                imported = self._import_regions(regions_to_import, options)
            
            self.stdout.write(self.style.SUCCESS(f"\n✓ Successfully imported {imported} region(s)!\n"))
        
        except FileNotFoundError:
            raise CommandError(f"File not found: {input_file}")
        except json.JSONDecodeError:
            raise CommandError(f"Invalid JSON file: {input_file}")
        except Exception as e:
            raise CommandError(f"Error importing configurations: {str(e)}")

    def _load_json(self, file_path):
        """Load regions from JSON file."""
        with open(file_path, 'r') as f:
            return json.load(f)

    def _load_csv(self, file_path):
        """Load regions from CSV file."""
        regions = []
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                regions.append({
                    'code': row['Code'],
                    'name': row['Name'],
                    'default_language': row['Language'],
                    'timezone': row['Timezone'],
                    'date_format': row['Date Format'],
                    'grading_scale': row['Grading Scale'],
                    'default_currency': row['Currency'],
                    'academic_year_start_month': int(row['Year Start (Month)']),
                    'term_count_per_year': int(row['Terms/Year']),
                    'enable_online_admissions': row['Admissions'].lower() == 'yes',
                    'enable_parent_portal': row['Parent Portal'].lower() == 'yes',
                    'enable_student_portal': row['Student Portal'].lower() == 'yes',
                })
        return regions

    def _validate_import_data(self, regions):
        """Validate region data before import."""
        errors = []
        
        for i, region in enumerate(regions):
            # Check required fields
            required_fields = ['code', 'name', 'timezone', 'default_currency']
            for field in required_fields:
                if not region.get(field):
                    errors.append(f"Region {i+1}: Missing required field '{field}'")
            
            # Validate code format
            if region.get('code') and not (len(region['code']) <= 10):
                errors.append(f"Region {i+1}: Code too long (max 10 characters)")
            
            # Validate month range
            month = region.get('academic_year_start_month')
            if month and not (1 <= month <= 12):
                errors.append(f"Region {i+1}: Invalid academic_year_start_month ({month})")
            
            # Validate term count
            terms = region.get('term_count_per_year')
            if terms and not (1 <= terms <= 4):
                errors.append(f"Region {i+1}: Invalid term_count_per_year ({terms})")
        
        return errors

    def _check_conflicts(self, regions, options):
        """Check for existing regions that would conflict."""
        conflicts = []
        
        for region in regions:
            if RegionConfig.objects.filter(code=region['code']).exists():
                conflicts.append(f"Region code '{region['code']}' already exists")
        
        return conflicts

    def _import_regions(self, regions, options):
        """Import regions into database."""
        imported = 0
        
        for region_data in regions:
            code = region_data['code']
            
            # Check if exists
            existing = RegionConfig.objects.filter(code=code).first()
            if existing:
                if options['overwrite']:
                    existing.delete()
                elif options['merge']:
                    # Update existing
                    for key, value in region_data.items():
                        if key != 'code' and key != 'grading_scales':
                            setattr(existing, key, value)
                    existing.save()
                    imported += 1
                    continue
                else:
                    continue
            
            # Create new region
            region_obj = RegionConfig.objects.create(
                code=code,
                name=region_data['name'],
                default_language=region_data.get('default_language', 'en'),
                timezone=region_data['timezone'],
                date_format=region_data.get('date_format', 'YYYY-MM-DD'),
                grading_scale=region_data.get('grading_scale', '0-20'),
                default_currency=region_data['default_currency'],
                academic_year_start_month=region_data.get('academic_year_start_month', 9),
                term_count_per_year=region_data.get('term_count_per_year', 3),
                enable_online_admissions=region_data.get('enable_online_admissions', False),
                enable_parent_portal=region_data.get('enable_parent_portal', False),
                enable_student_portal=region_data.get('enable_student_portal', False),
            )
            
            # Import grading scales if present
            if 'grading_scales' in region_data:
                for scale in region_data['grading_scales']:
                    GradingScaleConfig.objects.create(
                        region=region_obj,
                        scale_type=scale['scale_type'],
                        min_score=Decimal(scale['min_score']),
                        max_score=Decimal(scale['max_score']),
                        grade_a_min=Decimal(scale['grade_a_min']),
                        grade_b_min=Decimal(scale['grade_b_min']),
                        grade_c_min=Decimal(scale['grade_c_min']),
                        grade_d_min=Decimal(scale['grade_d_min']),
                        grade_f_min=Decimal(scale['grade_f_min']),
                        display_format=scale.get('display_format', '0.00'),
                    )
            
            imported += 1
        
        return imported
