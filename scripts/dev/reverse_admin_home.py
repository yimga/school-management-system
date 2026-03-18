# Run from project root: python scripts/dev/reverse_admin_home.py
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.urls import reverse

print(reverse("admin:home"))
