import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from django.template import engines
engine = engines['django']
tpl = engine.from_string('{% load breadcrumb_extras %}{{ \'/a/b/\'|split:\'/\' }}')
print(tpl.render({}))
