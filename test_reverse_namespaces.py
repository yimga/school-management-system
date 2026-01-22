import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.urls import reverse
namespaces = ['admin','accounts','backend','portal','kb','reports','analytics','finance','payroll','compliance','siteconfig','api','auth']
for ns in namespaces:
    try:
        print(ns, reverse('home', current_app=ns))
    except Exception as exc:
        print(ns, type(exc).__name__)
