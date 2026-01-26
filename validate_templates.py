import os, django, traceback
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from django.template.loader import get_template
from django.template import TemplateSyntaxError
base = Path('templates')
for tpl in base.rglob('*.html'):
    rel = tpl.relative_to(base)
    try:
        get_template(str(rel))
    except TemplateSyntaxError as e:
        print('ERROR', tpl)
        traceback.print_exc()
    except Exception as exc:
        print('OTHER', tpl, type(exc).__name__, exc)
