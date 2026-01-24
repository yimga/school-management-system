#!/usr/bin/env python
"""
Quick test script to verify admin page access and key URLs
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()

# Create test client
client = Client()

# Test URLs
urls_to_test = [
    ('/', 'Home'),
    ('/admin/', 'Admin Index'),
    ('/authentication/login/', 'Login'),
    ('/authentication/backend/', 'Backend Dashboard'),
]

print("=" * 60)
print("URL ACCESSIBILITY TEST")
print("=" * 60)

for url, name in urls_to_test:
    try:
        response = client.get(url, follow=True)
        status = "✓ OK" if response.status_code < 400 else f"✗ ERROR {response.status_code}"
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else url
        print(f"{status:15} {name:25} {url}")
        if response.redirect_chain:
            print(f"                → Redirected to: {final_url}")
    except Exception as e:
        print(f"✗ FAILED       {name:25} {url}")
        print(f"                Error: {str(e)}")
    print()

print("=" * 60)
print("ADMIN SITE CHECK")
print("=" * 60)

from config.admin import admin_site
print(f"Admin site class: {admin_site.__class__.__name__}")
print(f"Registered models: {len(admin_site._registry)}")
print(f"Sample models: {list(admin_site._registry.keys())[:5]}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
