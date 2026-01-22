from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.siteconfig.models import RegionConfig
from apps.compliance.models import RegionalComplianceRequirement

class Command(BaseCommand):
    help = 'Check regional compliance status'
    
    def add_arguments(self, parser):
        parser.add_argument('--region', type=str, help='Region code')
        parser.add_argument('--all-regions', action='store_true')
    
    def handle(self, *args, **options):
        self.stdout.write('[+] Compliance Status Check')
        if options['all_regions']:
            regions = RegionConfig.objects.all()
        else:
            regions = [RegionConfig.objects.get(code=options['region'])]
        
        for region in regions:
            reqs = RegionalComplianceRequirement.objects.filter(region=region)
            self.stdout.write(f"[*] {region.name}: {reqs.count()} requirements")
        
        self.stdout.write('[+] Done')
