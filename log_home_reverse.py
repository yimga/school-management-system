import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['ALLOWED_HOSTS'] = 'testserver,localhost,127.0.0.1'
import django
django.setup()
import inspect, traceback
from django.urls import base
from django.urls.exceptions import NoReverseMatch
orig_reverse = base.reverse

def logging_reverse(viewname, *args, **kwargs):
    try:
        return orig_reverse(viewname, *args, **kwargs)
    except NoReverseMatch as exc:
        if viewname == 'home':
            stack = ''.join(traceback.format_stack(limit=10))
            print('NoReverseMatch for "home" stack:\n', stack)
        raise

base.reverse = logging_reverse

from django.test import Client
from django.contrib.auth import get_user_model
User = get_user_model()
user, _ = User.objects.get_or_create(username='admin')
user.set_password('admin123')
user.is_staff = True
user.is_superuser = True
user.save()
client = Client()
client.login(username='admin', password='admin123')
try:
    client.get('/admin/')
except Exception as exc:
    print('Exception caught', exc)
