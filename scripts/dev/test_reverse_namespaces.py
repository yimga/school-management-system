# Run from project root: python scripts/dev/test_reverse_namespaces.py
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.urls import reverse

namespaces = [
    "admin",
    "accounts",
    "backend",
    "portal",
    "kb",
    "reports",
    "analytics",
    "finance",
    "payroll",
    "compliance",
    "siteconfig",
    "api",
    "auth",
]
for ns in namespaces:
    try:
        print(ns, reverse("home", current_app=ns))
    except Exception as exc:
        print(ns, type(exc).__name__)
