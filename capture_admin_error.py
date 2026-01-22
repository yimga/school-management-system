import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['ALLOWED_HOSTS'] = 'testserver,localhost,127.0.0.1'
import django
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model
User = get_user_model()
user, created = User.objects.get_or_create(username='admin')
user.set_password('admin123')
user.is_staff = True
user.is_superuser = True
user.save()
client = Client()
client.login(username='admin', password='admin123')
client.raise_request_exception = False
response = client.get('/admin/')
print('status', response.status_code)
print(response.content.decode())
