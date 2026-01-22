"""
Clone a region configuration with all its grading scales.
Usage: python manage.py clone_region CMR NEW_REGION --name "My New Region"
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.siteconfig.models import RegionConfig, GradingScaleConfig


class Command(BaseCommand):
    help = 'Clone a region configuration with all its settings and grading scales'

    def add_arguments(self, parser):
        parser.add_argument('source_code', type=str, help='Source region code to clone')
        parser.add_argument('new_code', type=str, help='New region code')
        parser.add_argument(
            '--name',
            type=str,
            help='New region name (default: "{source_name} (Copy)")',
        )
        parser.add_argument(
            '--skip-scales',
            action='store_true',
            help='Skip cloning grading scales',
        )

    def handle(self, *args, **options):
        source_code = options['source_code']
        new_code = options['new_code']
        
        self.stdout.write(self.style.SUCCESS('\n🔄 Region Cloning Tool\n'))
        
        # Get source region
        try:
            source_region = RegionConfig.objects.get(code=source_code)
        except RegionConfig.DoesNotExist:
            raise CommandError(f"Source region '{source_code}' not found")
        
        # Check if new region already exists
        if RegionConfig.objects.filter(code=new_code).exists():
            raise CommandError(f"Region with code '{new_code}' already exists")
        
        # Prepare new region data
        new_name = options.get('name') or f"{source_region.name} (Copy)"
        
        self.stdout.write(f"Source:  {source_region.code} - {source_region.name}")
        self.stdout.write(f"Target:  {new_code} - {new_name}")
        self.stdout.write('-' * 60)
        
        try:
            with transaction.atomic():
                # Create new region
                new_region = RegionConfig.objects.create(
                    code=new_code,
                    name=new_name,
                    default_language=source_region.default_language,
                    timezone=source_region.timezone,
                    date_format=source_region.date_format,
                    grading_scale=source_region.grading_scale,
                    default_currency=source_region.default_currency,
                    academic_year_start_month=source_region.academic_year_start_month,
                    term_count_per_year=source_region.term_count_per_year,
                    enable_online_admissions=source_region.enable_online_admissions,
                    enable_parent_portal=source_region.enable_parent_portal,
                    enable_student_portal=source_region.enable_student_portal,
                )
                self.stdout.write(self.style.SUCCESS('✓ Created new region'))
                
                # Clone grading scales
                if not options['skip_scales']:
                    scales_created = 0
                    for scale in source_region.gradingscaleconfig_set.all():
                        GradingScaleConfig.objects.create(
                            region=new_region,
                            scale_type=scale.scale_type,
                            min_score=scale.min_score,
                            max_score=scale.max_score,
                            grade_a_min=scale.grade_a_min,
                            grade_b_min=scale.grade_b_min,
                            grade_c_min=scale.grade_c_min,
                            grade_d_min=scale.grade_d_min,
                            grade_f_min=scale.grade_f_min,
                            display_format=scale.display_format,
                        )
                        scales_created += 1
                    
                    self.stdout.write(self.style.SUCCESS(f'✓ Cloned {scales_created} grading scales'))
                
                self.stdout.write('-' * 60)
                self.stdout.write(self.style.SUCCESS(f'✓ Region "{new_name}" ({new_code}) cloned successfully!\n'))
                
        except Exception as e:
            raise CommandError(f"Error cloning region: {str(e)}")
