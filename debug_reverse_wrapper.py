import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['ALLOWED_HOSTS'] = 'testserver,localhost,127.0.0.1'
import django
django.setup()
import inspect, traceback
from django.urls import reverse as django_reverse
from django.urls import reverse_lazy as django_reverse_lazy

def wrap_reverse(func, name):
    def inner(viewname, *args, **kwargs):
        if viewname == 'home':
            frame = inspect.stack()[1]
            print(f"{name}('home') called from {frame.filename}:{frame.lineno}")
            traceback.print_stack(limit=5)
        return func(viewname, *args, **kwargs)
    return inner

import django.urls
django.urls.reverse = wrap_reverse(django_reverse, 'reverse')
django.urls.reverse_lazy = wrap_reverse(django_reverse_lazy, 'reverse_lazy')

from django.contrib.auth import get_user_model
User = get_user_model()
user, created = User.objects.get_or_create(username='admin')
user.set_password('admin123')
user.is_staff = True
user.is_superuser = True
user.save()

from django.test import Client
client = Client()
client.login(username='admin', password='admin123')
try:
    client.get('/admin/')
except Exception as exc:
    print('exception', exc)
