"""Management command to generate legal documents in multiple languages."""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.global_registries.models import RegionConfig
from apps.compliance.models import LegalDocument

class Command(BaseCommand):
    help = 'Generate legal documents for regions'

    def add_arguments(self, parser):
        parser.add_argument('--region', type=str)
        parser.add_argument('--all-regions', action='store_true')
        parser.add_argument('--document-type', type=str, choices=['privacy_policy', 'terms_of_service', 'data_agreement'])
        parser.add_argument('--language', type=str, choices=['en', 'fr', 'sw', 'yo', 'pid', 'ha'])
        parser.add_argument('--overwrite', action='store_true')

    def handle(self, *args, **options):
        if not options['region'] and not options['all_regions']:
            raise CommandError('Specify --region or --all-regions')
        
        regions = RegionConfig.objects.all() if options['all_regions'] else [RegionConfig.objects.get(code=options['region'])]
        doc_types = [options['document_type']] if options['document_type'] else ['privacy_policy', 'terms_of_service', 'data_agreement']
        languages = [options['language']] if options['language'] else ['en', 'fr', 'sw', 'yo', 'pid', 'ha']
        
        created = 0
        for region in regions:
            for doc_type in doc_types:
                for lang in languages:
                    existing = LegalDocument.objects.filter(region=region, document_type=doc_type, language=lang, is_active=True).first()
                    if existing and not options['overwrite']:
                        continue
                    
                    version = (existing.version + 1) if existing else 1
                    LegalDocument.objects.create(
                        region=region,
                        document_type=doc_type,
                        language=lang,
                        title=f"{doc_type} ({lang})",
                        content=f"<h1>{doc_type}</h1><p>Content in {lang}</p>",
                        version=version,
                        effective_date=timezone.now().date(),
                        is_active=True
                    )
                    self.stdout.write(self.style.SUCCESS(f"[+] {doc_type} ({lang}) v{version}"))
                    created += 1
        
        self.stdout.write(f"Created: {created}")
        self.stdout.write(self.style.SUCCESS('[+] Done'))
