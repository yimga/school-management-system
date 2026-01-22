import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['ALLOWED_HOSTS'] = 'testserver,localhost,127.0.0.1'
import django
django.setup()
from django.urls import reverse as django_reverse
import inspect, traceback

def reverse_wrapper(viewname, *args, **kwargs):
    if viewname == 'home':
        frame = inspect.stack()[1]
        print('reverse("home") called from', frame.filename, 'line', frame.lineno)
        traceback.print_stack(limit=5)
    return django_reverse(viewname, *args, **kwargs)

import django.urls
django.urls.reverse = reverse_wrapper

def ensure_superuser():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user, created = User.objects.get_or_create(username='admin', defaults={'email': 'admin@example.com'})
    user.set_password('admin123')
    user.is_superuser = True
    user.is_staff = True
    user.save()

ensure_superuser()
from django.test import Client
client = Client()
client.login(username='admin', password='admin123')
try:
    client.get('/admin/')
except Exception as exc:
    print('exception', exc)
