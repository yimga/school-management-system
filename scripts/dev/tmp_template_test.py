# Run from project root: python scripts/dev/tmp_template_test.py
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.template import engines

engine = engines["django"]
tpl = engine.from_string("{% load breadcrumb_extras %}{{ '/a/b/'|split:'/' }}")
print(tpl.render({}))
