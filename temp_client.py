import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser(username='admin', email='admin@example.com', password='admin123')
client = Client()
if client.login(username='admin', password='admin123'):
    response = client.get('/admin/')
    print('status', response.status_code)
    print(response.content.decode()[:500])
else:
    print('login failed')
