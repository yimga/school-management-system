#!/usr/bin/env python
"""Quick script to test /backend URL access. Run from project root: python scripts/dev/test_backend_url.py"""
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, '..', '..'))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.urls import reverse, resolve
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()

print("=" * 60)
print("Testing /backend URL Configuration")
print("=" * 60)

try:
    print("\n1. Testing URL: /backend/")
    match = resolve('/backend/')
    print(f"   ✓ Resolves to: {match.url_name}")
    print(f"   ✓ View: {match.func}")
    print("\n2. Testing URL: /authentication/backend/")
    match = resolve('/authentication/backend/')
    print(f"   ✓ Resolves to: accounts:{match.url_name}")
    print(f"   ✓ View: {match.func.__name__}")
    print("\n3. Testing named URL reverse: 'accounts:backend_dashboard'")
    url = reverse('accounts:backend_dashboard')
    print(f"   ✓ Reverse URL: {url}")
    print("\n4. Access Requirements:")
    print("   - User must be authenticated")
    print("   - User must be: superuser OR staff OR role='ADMIN'")
    print("   - User must have 'settings.manage' permission")
    print("\n5. URL Flow:")
    print("   /backend/ → redirects to → /authentication/backend/")
    print("   /authentication/backend/ → renders backend_dashboard view")
    print("\n✅ All URL configurations are correct!")
    print("\nTo access /backend, make sure you:")
    print("  1. Log in as a superuser/staff/admin user")
    print("  2. Have the 'settings.manage' permission")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("=" * 60)
