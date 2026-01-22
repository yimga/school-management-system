from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.siteconfig.models import RegionConfig
from apps.compliance.models import LegalDocument

class Command(BaseCommand):
    help = 'Generate legal documents'
    
    def add_arguments(self, parser):
        parser.add_argument('--region', type=str)
        parser.add_argument('--all-regions', action='store_true')
    
    def handle(self, *args, **options):
        self.stdout.write('[+] Generate Legal Documents')
        if options['all_regions']:
            regions = RegionConfig.objects.all()
        else:
            regions = [RegionConfig.objects.get(code=options['region'])]
        
        for region in regions:
            self.stdout.write(f"[*] {region.name}")
        
        self.stdout.write('[+] Done')
