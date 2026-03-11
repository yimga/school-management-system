"""Management command to check regional compliance status."""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.global_registries.models import RegionConfig
from apps.compliance.models import RegionalComplianceRequirement, ComplianceAuditLog
from apps.compliance.validators import RegionalComplianceValidator

class Command(BaseCommand):
    help = 'Check compliance status for regions'

    def add_arguments(self, parser):
        parser.add_argument('--region', type=str, help='Region code')
        parser.add_argument('--all-regions', action='store_true', help='Check all regions')
        parser.add_argument('--status', type=str, choices=['pending', 'implemented', 'active'])
        parser.add_argument('--generate-report', action='store_true')
        parser.add_argument('--check-overdue', action='store_true')

    def handle(self, *args, **options):
        if not options['region'] and not options['all_regions']:
            raise CommandError('Specify --region or --all-regions')
        
        regions = RegionConfig.objects.all() if options['all_regions'] else [RegionConfig.objects.get(code=options['region'])]
        
        for region in regions:
            reqs = RegionalComplianceRequirement.objects.filter(region=region)
            if options['status']:
                reqs = reqs.filter(status=options['status'])
            
            self.stdout.write(f"[*] {region.name} ({region.code})")
            validator = RegionalComplianceValidator(region)
            validator.validate_region_compliance(reqs)
            score = validator.generate_compliance_score(reqs)
            self.stdout.write(f"    Score: {score}%")
            
            if options['check_overdue']:
                overdue = [r for r in reqs if r.is_overdue()]
                if overdue:
                    self.stdout.write(f"    [!] {len(overdue)} overdue")
        
        self.stdout.write(self.style.SUCCESS('[+] Done'))
