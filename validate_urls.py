#!/usr/bin/env python
"""
URL Validation Script
Validates all URLs and internal links in the Django project
"""
import os
import django
import re
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.urls import get_resolver
from django.urls.exceptions import Resolver404

def get_all_url_patterns():
    """Get all URL patterns from Django URLconf"""
    resolver = get_resolver()
    patterns = []
    
    def extract_patterns(urlconf, prefix=''):
        for pattern in urlconf.url_patterns:
            if hasattr(pattern, 'url_patterns'):
                # This is a URLResolver (nested patterns)
                new_prefix = prefix + str(pattern.pattern)
                extract_patterns(pattern, new_prefix)
            else:
                # This is a URLPattern
                full_path = prefix + str(pattern.pattern)
                patterns.append({
                    'path': str(full_path),
                    'name': pattern.name or 'unnamed',
                    'pattern': pattern
                })
    
    extract_patterns(resolver)
    return patterns

def validate_template_links():
    """Scan all HTML templates for hard-coded links"""
    template_dir = Path('templates')
    broken_links = []
    valid_links = set()
    
    # Get all valid URL patterns
    url_patterns = get_all_url_patterns()
    valid_paths = {p['path'].replace('^', '').replace('$', '') for p in url_patterns}
    
    # Add common URL patterns
    valid_prefixes = {
        '/admin/',
        '/authentication/',
        '/api/',
        '/portal/',
        '/evals/',
        '/siteconfig/',
        '/reports/',
        '/analytics/',
        '/finance/',
        '/payroll/',
        '/compliance/',
        '/kb/',
        '/',
    }
    
    if template_dir.exists():
        for html_file in template_dir.rglob('*.html'):
            try:
                with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue
                
            # Find all href links
            links = re.findall(r'href=["\']([^"\']+)["\']', content)
            
            for link in links:
                # Skip dynamic URLs with variables or template literals
                if '{{' in link or '{%' in link or '<' in link or '${' in link or '$(' in link:
                    continue
                
                # Skip external links
                if link.startswith('http'):
                    continue
                
                # Skip empty, anchors, or JS links
                if not link or link.startswith('#') or link.startswith('?') or link.lower().startswith('javascript:'):
                    continue
                
                # Skip mailto/tel/data links
                if link.lower().startswith(('mailto:', 'tel:', 'data:')):
                    continue
                
                # Check if it's a valid URL prefix
                valid = False
                for prefix in valid_prefixes:
                    if link.startswith(prefix):
                        valid = True
                        break
                
                if not valid:
                    broken_links.append({
                        'file': str(html_file),
                        'link': link
                    })
                else:
                    valid_links.add(link)
    
    return broken_links, valid_links

def main():
    print("=" * 80)
    print("DJANGO URL VALIDATION REPORT")
    print("=" * 80)
    print()
    
    # Get all URL patterns
    print("[OK] Registered URL Patterns:")
    print("-" * 80)
    patterns = get_all_url_patterns()
    for pattern in sorted(patterns, key=lambda x: x['path'])[:30]:
        print(f"  {pattern['path']:<40} [{pattern['name']}]")
    print(f"\n  Total patterns: {len(patterns)}")
    print()
    
    # Check template links
    print("[OK] Template Link Validation:")
    print("-" * 80)
    broken, valid = validate_template_links()
    
    print(f"  Valid links found: {len(valid)}")
    for link in sorted(list(valid))[:20]:
        print(f"    [OK] {link}")
    
    if broken:
        print(f"\n  ⚠ Potentially broken links found: {len(broken)}")
        for item in broken[:10]:
            print(f"    [FAIL] {item['link']} in {item['file']}")
    else:
        print("\n  [OK] No obviously broken links detected")
    
    print()
    print("=" * 80)
    print("KEY ROUTE VALIDATIONS:")
    print("=" * 80)
    
    # Critical routes (plan Phase 0: six URLs that must resolve)
    critical_routes = [
        ('/', 'home'),
        ('/authentication/login/', 'login'),
        ('/admin/', 'backend admin'),
        ('/portal/parent/', 'parent dashboard'),
        ('/evals/teacher/', 'teacher dashboard'),
        ('/backend/', 'frontend admin redirect'),
        ('/authentication/backend/', 'frontend admin dashboard'),
        ('/siteconfig/customizer/', 'site customizer'),
    ]
    
    for route, description in critical_routes:
        try:
            resolver = get_resolver()
            resolver.resolve(route)
            print(f"  [OK] {route:<40} [{description}]")
        except Resolver404:
            print(f"  [FAIL] {route:<40} [{description}] - NOT FOUND")
    
    print()

if __name__ == '__main__':
    main()
