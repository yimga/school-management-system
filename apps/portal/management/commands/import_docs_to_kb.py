"""
Management command to import documentation files into Knowledge Base
Converts markdown files from docs/ directory into KB articles
"""
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, OperationalError, ProgrammingError

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.portal.models_kb import KBCategory, KBArticle
from apps.portal.sanitizers import sanitize_html

# Admin user resolve (User.objects.filter).
_KB_IMPORT_ADMIN_RESOLVE_ERRORS = (
    DatabaseError,
    OperationalError,
    ProgrammingError,
    AttributeError,
    TypeError,
)
# File processing (create/save, file read, slugify).
_KB_IMPORT_FILE_PROCESSING_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValidationError,
    OSError,
    IOError,
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
    UnicodeDecodeError,
)
# Markdown library convert (md.convert).
_KB_IMPORT_MARKDOWN_CONVERT_ERRORS = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    IndexError,
)

# Try to import markdown, fallback to simple conversion if not available
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    import warnings
    warnings.warn("markdown library not found. Using simple markdown conversion.")

User = get_user_model()


class Command(BaseCommand):
    help = 'Import documentation files from docs/ directory into Knowledge Base'

    def add_arguments(self, parser):
        parser.add_argument(
            '--category',
            type=str,
            help='Category slug to import into (creates if not exists)',
            default='system-admin',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing articles with same slug',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing',
        )
        parser.add_argument(
            '--include-root',
            action='store_true',
            help='Also import selected operator-facing markdown files from repo root.',
        )
        parser.add_argument(
            '--generate-odt',
            action='store_true',
            help='Generate LibreOffice ODT files after import (KB articles).',
        )
        parser.add_argument(
            '--odt-engine',
            type=str,
            default='auto',
            choices=['auto', 'libreoffice', 'pandoc'],
            help='ODT conversion engine to use when --generate-odt is set.',
        )
        parser.add_argument(
            '--odt-toc',
            action='store_true',
            help='Include table of contents in ODT output (Pandoc only).',
        )

    def _safe_write(self, message: str):
        """Write to stdout, falling back to safe replacement on Windows consoles."""
        if message is None:
            return
        try:
            self.stdout.write(message)
        except UnicodeEncodeError:
            encoding = getattr(self.stdout, "encoding", None) or "utf-8"
            safe = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
            self.stdout.write(safe)

    def handle(self, *args, **options):
        self._safe_write(self.style.SUCCESS('Starting documentation import...'))
        
        # Get base directory
        base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        docs_dir = base_dir / 'docs'
        
        if not docs_dir.exists():
            self._safe_write(self.style.ERROR(f'Docs directory not found: {docs_dir}'))
            return
        
        # Operator Manual structure (global, region-configurable)
        # This keeps docs organized and discoverable without duplicating content.
        operator_root_slug = options["category"]
        operator_root, created = KBCategory.objects.get_or_create(
            slug=operator_root_slug,
            defaults={
                "name": self._slug_to_name(operator_root_slug),
                "description": "Operator Manual: guided workflows and practical how-to articles.",
                "icon": "fa-book",
                "display_order": 1,
                "is_active": True,
                "target_roles": [],
            },
        )
        if created:
            self._safe_write(self.style.SUCCESS(f"Created root KB category: {operator_root.name}"))
        else:
            self._safe_write(f"Using existing root KB category: {operator_root.name}")

        # Child categories as proposed in the plan
        operator_categories = [
            ("getting-started", "Getting Started", "fa-rocket", 1),
            ("year-setup", "Year Setup (by region)", "fa-calendar-alt", 2),
            ("onboarding", "Onboarding (Students, Teachers, Parents)", "fa-user-plus", 3),
            ("academics", "Academics (Assignments, Marks, OCR)", "fa-graduation-cap", 4),
            ("approvals-audits", "Approvals & Audits", "fa-shield-alt", 5),
            ("reports", "Reports (Styles, Publishing)", "fa-file-alt", 6),
            ("communication", "Communication (Messaging, Groups, Announcements)", "fa-comments", 7),
            ("document-library", "Document Library", "fa-folder-open", 8),
            ("troubleshooting", "Troubleshooting", "fa-life-ring", 99),
        ]
        for slug, name, icon, order in operator_categories:
            KBCategory.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": f"Operator manual: {name}",
                    "icon": icon,
                    "display_order": order,
                    "parent": operator_root,
                    "is_active": True,
                    "target_roles": [],
                },
            )
        
        # Get admin user for author
        try:
            admin_user = User.objects.filter(is_superuser=True).first()
            if not admin_user:
                admin_user = User.objects.filter(is_staff=True).first()
        except _KB_IMPORT_ADMIN_RESOLVE_ERRORS:
            log_exception_with_context(
                "import_docs_to_kb: resolve admin user failed (non-fatal)",
                extra={"command": "import_docs_to_kb"},
            )
            admin_user = None
        
        # Map documentation files to categories and metadata
        doc_mapping = self._get_doc_mapping()
        
        imported_count = 0
        skipped_count = 0
        
        def iter_source_files():
            # docs/
            for p in sorted(docs_dir.glob("*.md")):
                yield p
            # selected root docs (operator-facing)
            if options.get("include_root"):
                root_allowlist = [
                    "QUICK_START.md",
                    "URL_QUICK_REFERENCE.md",
                    "API_QUICK_REFERENCE.md",
                    "MOBILE_QUICK_SUMMARY.md",
                ]
                for name in root_allowlist:
                    candidate = base_dir / name
                    if candidate.exists():
                        yield candidate

        # Process each markdown file
        for md_file in iter_source_files():
            # Skip KB files that are already in KB format
            if md_file.name.startswith('KB_'):
                self._safe_write(f'  [SKIP] Skipping KB file: {md_file.name}')
                continue
            
            # Skip implementation guides and checklists (these are for developers)
            skip_patterns = [
                'IMPLEMENTATION_GUIDE',
                'CHECKLIST',
                'ROADMAP',
                'COMPLETION',
                'INDEX',
                'ANALYSIS',
                'TESTING',
                'READY_FOR_TESTING',
            ]
            explicit_mapping = md_file.name in doc_mapping
            if (not explicit_mapping) and any(pattern in md_file.name.upper() for pattern in skip_patterns):
                self._safe_write(f'  [SKIP] Skipping developer doc: {md_file.name}')
                continue
            
            # Get metadata for this file
            file_metadata = doc_mapping.get(md_file.name, {})
            target_category_slug = file_metadata.get("category", operator_root_slug)
            difficulty = file_metadata.get('difficulty', 'INTERMEDIATE')
            tags = file_metadata.get('tags', '')
            
            # Use specific category if provided
            if target_category_slug != operator_root_slug:
                target_category, _ = KBCategory.objects.get_or_create(
                    slug=target_category_slug,
                    defaults={
                        'name': self._slug_to_name(target_category_slug),
                        'description': f'Documentation for {self._slug_to_name(target_category_slug)}',
                        'icon': file_metadata.get('icon', 'fa-book'),
                        'display_order': file_metadata.get('order', 10),
                        "parent": operator_root,
                        "is_active": True,
                        "target_roles": [],
                    }
                )
            else:
                target_category = operator_root
            
            # Read and convert markdown
            try:
                content = md_file.read_text(encoding='utf-8')
                title, summary, html_content = self._process_markdown(content, md_file.name)
                
                # Generate slug from filename
                slug = slugify(md_file.stem)
                
                if options['dry_run']:
                    self._safe_write(f'  -> Would import: {title} (slug: {slug})')
                    imported_count += 1
                    continue
                
                # Check if article exists
                existing = KBArticle.objects.filter(slug=slug).first()
                if existing and not options['overwrite']:
                    self._safe_write(f'  [SKIP] Skipping existing: {title} (use --overwrite to update)')
                    skipped_count += 1
                    continue
                
                # Create or update article
                article_data = {
                    'title': title,
                    'slug': slug,
                    'category': target_category,
                    'summary': summary,
                    'content': content,  # Keep original markdown
                    'content_html': html_content,
                    'difficulty': difficulty,
                    'tags': tags,
                    'status': 'PUBLISHED',
                    'estimated_read_time': self._estimate_read_time(content),
                }
                
                if admin_user:
                    article_data['author'] = admin_user
                
                if existing:
                    for key, value in article_data.items():
                        setattr(existing, key, value)
                    existing.save()
                    self._safe_write(self.style.SUCCESS(f'  [OK] Updated: {title}'))
                else:
                    KBArticle.objects.create(**article_data)
                    self._safe_write(self.style.SUCCESS(f'  [OK] Created: {title}'))
                
                imported_count += 1
                
            except _KB_IMPORT_FILE_PROCESSING_ERRORS as e:
                log_exception_with_context(
                    "import_docs_to_kb: error processing file",
                    extra={"command": "import_docs_to_kb", "file": md_file.name},
                )
                self._safe_write(self.style.ERROR(f'  [ERROR] Error processing {md_file.name}: {e}'))
        
        self._safe_write('')
        self._safe_write(self.style.SUCCESS(f'Import complete!'))
        self._safe_write(f'  Imported: {imported_count}')
        self._safe_write(f'  Skipped: {skipped_count}')

        if options.get("generate_odt"):
            self._safe_write("")
            self._safe_write(self.style.SUCCESS("Generating ODT exports for KB articles..."))
            cmd_args = ["--all", "--engine", options.get("odt_engine", "auto")]
            if options.get("overwrite"):
                cmd_args.append("--overwrite")
            if options.get("odt_toc"):
                cmd_args.append("--toc")
            call_command("generate_kb_odt", *cmd_args)
    
    def _get_doc_mapping(self):
        """Map documentation files to categories and metadata"""
        return {
            # Getting Started
            'ADMISSION_NUMBER_GUIDE.md': {
                'category': 'onboarding',
                'difficulty': 'INTERMEDIATE',
                'tags': 'admission, registration, student management, configuration',
                'icon': 'fa-user-plus',
                'order': 1,
            },
            'TESTING_CHECKLIST_ONBOARDING.md': {
                'category': 'getting-started',
                'difficulty': 'BEGINNER',
                'tags': 'testing, onboarding, checklist',
                'icon': 'fa-check-circle',
                'order': 2,
            },
            'ONBOARDING_READY_FOR_TESTING.md': {
                'category': 'getting-started',
                'difficulty': 'BEGINNER',
                'tags': 'onboarding, testing, setup',
                'icon': 'fa-rocket',
                'order': 3,
            },
            
            # Admin / configuration (operator-facing subset)
            'customization.md': {
                'category': 'getting-started',
                'difficulty': 'INTERMEDIATE',
                'tags': 'customization, settings, branding, theme',
                'icon': 'fa-cogs',
                'order': 1,
            },
            'SETUP_NEW_SCHOOL_WORLDWIDE.md': {
                'category': 'year-setup',
                'difficulty': 'ADVANCED',
                'tags': 'setup, configuration, deployment, installation',
                'icon': 'fa-globe',
                'order': 2,
            },
            'PHASE_1_2_5_ADMIN_GUIDE.md': {
                'category': 'year-setup',
                'difficulty': 'INTERMEDIATE',
                'tags': 'admin, regional configuration, management',
                'icon': 'fa-user-shield',
                'order': 3,
            },
            
            # Academics
            'MARKSHEET_OCR_SETUP.md': {
                'category': 'academics',
                'difficulty': 'INTERMEDIATE',
                'tags': 'marks, ocr, marksheet, setup, evaluations',
                'icon': 'fa-camera',
                'order': 4,
            },
            'KB_MARKSHEET_OCR_INSTALL.md': {
                'category': 'academics',
                'difficulty': 'INTERMEDIATE',
                'tags': 'marks, ocr, marksheet, install, evaluations',
                'icon': 'fa-camera',
                'order': 5,
            },
            'PHASE_1_2_4_INTERNATIONALIZATION.md': {
                'category': 'getting-started',
                'difficulty': 'ADVANCED',
                'tags': 'i18n, internationalization, languages, regions',
                'icon': 'fa-language',
                'order': 2,
            },
            
            # Finance
            'finance-payments.md': {
                'category': 'getting-started',
                'difficulty': 'INTERMEDIATE',
                'tags': 'finance, payments, fees, transactions',
                'icon': 'fa-coins',
                'order': 1,
            },
            'payroll-automation.md': {
                'category': 'getting-started',
                'difficulty': 'ADVANCED',
                'tags': 'payroll, automation, staff payments',
                'icon': 'fa-money-bill-wave',
                'order': 2,
            },
            
            # Reports
            'PHASE_1_2_7_REPORT_LOCALIZATION.md': {
                'category': 'reports',
                'difficulty': 'INTERMEDIATE',
                'tags': 'reports, localization, regional',
                'icon': 'fa-file-alt',
                'order': 1,
            },
            'KB_REPORT_STYLE_PREVIEW.md': {
                'category': 'reports',
                'difficulty': 'BEGINNER',
                'tags': 'reports, styles, preview, templates',
                'icon': 'fa-file-alt',
                'order': 2,
            },
            
            # Communication
            'ux.md': {
                'category': 'communication',
                'difficulty': 'BEGINNER',
                'tags': 'ux, user experience, interface',
                'icon': 'fa-comments',
                'order': 1,
            },
            'MESSAGING_GROUP_OPTIONS.md': {
                'category': 'communication',
                'difficulty': 'BEGINNER',
                'tags': 'messaging, groups, announcements, communication',
                'icon': 'fa-comments',
                'order': 2,
            },
            
            # Security & Compliance
            'security-checklist.md': {
                'category': 'approvals-audits',
                'difficulty': 'ADVANCED',
                'tags': 'security, compliance, checklist',
                'icon': 'fa-shield-alt',
                'order': 10,
            },
            'PHASE_1_2_8_COMPLIANCE_LEGAL.md': {
                'category': 'approvals-audits',
                'difficulty': 'ADVANCED',
                'tags': 'compliance, legal, audit',
                'icon': 'fa-gavel',
                'order': 11,
            },
            
            # Mobile & API
            'MOBILE_API_HANDBOOK.md': {
                'category': 'getting-started',
                'difficulty': 'ADVANCED',
                'tags': 'mobile, api, integration',
                'icon': 'fa-mobile-alt',
                'order': 12,
            },
            
            # Accessibility
            'ACCESSIBILITY.md': {
                'category': 'getting-started',
                'difficulty': 'INTERMEDIATE',
                'tags': 'accessibility, a11y, inclusive design',
                'icon': 'fa-universal-access',
                'order': 13,
            },
        }
    
    def _process_markdown(self, content, filename):
        """Convert markdown to HTML and extract title/summary"""
        # Extract title from first H1 or filename
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title = filename.replace('.md', '').replace('_', ' ').replace('-', ' ').title()
        
        # Extract summary from first paragraph or first few lines
        lines = content.split('\n')
        summary = ''
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('[') and not line.startswith('!'):
                summary = line[:200]  # First 200 chars
                break
        
        if not summary:
            summary = f'Documentation for {title}'
        
        # Convert markdown to HTML
        if MARKDOWN_AVAILABLE:
            try:
                md = markdown.Markdown(extensions=[
                    'fenced_code',
                    'tables',
                    'codehilite',
                    'nl2br',
                    'sane_lists',
                ])
                html_content = md.convert(content)
            except _KB_IMPORT_MARKDOWN_CONVERT_ERRORS as e:
                log_exception_with_context(
                    "import_docs_to_kb: markdown conversion failed, using simple conversion",
                    extra={"command": "import_docs_to_kb"},
                )
                self._safe_write(self.style.WARNING(f'Markdown conversion error: {e}, using simple conversion'))
                html_content = self._simple_markdown_to_html(content)
        else:
            html_content = self._simple_markdown_to_html(content)
        
        # Sanitize HTML using the KB sanitizer
        html_content = sanitize_html(html_content)
        
        # Clean up HTML
        html_content = self._clean_html(html_content)
        
        return title, summary, html_content
    
    def _clean_html(self, html):
        """Clean and format HTML content"""
        # Add Bootstrap classes to tables
        html = re.sub(r'<table>', '<table class="table table-bordered table-striped">', html)
        
        # Add Bootstrap classes to code blocks
        html = re.sub(r'<pre><code class="language-(\w+)">', r'<pre><code class="language-\1">', html)
        
        # Wrap code blocks in proper containers
        html = re.sub(
            r'<pre><code>',
            '<div class="code-block"><pre><code>',
            html
        )
        html = re.sub(
            r'</code></pre>',
            '</code></pre></div>',
            html
        )
        
        return html
    
    def _estimate_read_time(self, content):
        """Estimate reading time in minutes (assuming 200 words per minute)"""
        word_count = len(content.split())
        return max(1, round(word_count / 200))
    
    def _slug_to_name(self, slug):
        """Convert slug to readable name"""
        return slug.replace('-', ' ').replace('_', ' ').title()
    
    def _simple_markdown_to_html(self, content):
        """Simple markdown to HTML conversion without external library"""
        html = content
        
        # Headers
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        
        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # Code blocks
        html = re.sub(r'```(\w+)?\n(.*?)```', r'<pre><code class="language-\1">\2</code></pre>', html, flags=re.DOTALL)
        html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
        
        # Links
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        
        # Lists
        html = re.sub(r'^\* (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        
        # Wrap consecutive list items in ul/ol
        html = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', html, flags=re.DOTALL)
        
        # Paragraphs (lines not already in tags)
        lines = html.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('<'):
                result.append(f'<p>{line}</p>')
            else:
                result.append(line)
        html = '\n'.join(result)
        
        return html
