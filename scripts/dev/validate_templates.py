# Run from project root: python scripts/dev/validate_templates.py
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

import django
from pathlib import Path
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.template.loader import get_template
from django.template import TemplateSyntaxError

base = Path("templates")
for tpl in base.rglob("*.html"):
    rel = tpl.relative_to(base)
    try:
        get_template(str(rel))
    except TemplateSyntaxError as e:
        print("ERROR", tpl)
        traceback.print_exc()
    except Exception as exc:
        print("OTHER", tpl, type(exc).__name__, exc)
