import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.urls import resolve
match = resolve('/admin/')
print('view_name', match.view_name)
print('namespace', match.namespace)
print('app_name', match.app_name)
print('url_name', match.url_name)
